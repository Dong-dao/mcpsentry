"""D3 验收测试：tools/call 拦截 + SOURCE 源标记。

经 stdio 连接代理（后端 taint_backend）：
- read_external_doc（SOURCE）调用被分配 call_id、分类记录为 source，
  返回值归一化+分块进入 TaintStore（JSONL 落盘），flow log 含完整污点源数据；
- echo（NEUTRAL）不产生污点记录；
- 工具分类可被覆盖文件改写。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from engine.taint.normalize import normalize

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "taint_backend.py"
sys.path.insert(0, str(FIXTURE.parent))
from taint_backend import DOC_TEXT  # noqa: E402


async def _run_proxy(
    flow_log: Path, taint_log: Path | None, classes: dict | None = None
) -> tuple[str, str, str]:
    backend = [sys.executable, str(FIXTURE)]
    cmd = [
        sys.executable,
        "-m",
        "engine.proxy",
        "--backend",
        json.dumps(backend),
        "--log",
        str(flow_log),
    ]
    if taint_log is not None:
        cmd += ["--taint-log", str(taint_log)]
    if classes is not None:
        classes_path = flow_log.parent / "classes.json"
        classes_path.write_text(json.dumps(classes), encoding="utf-8")
        cmd += ["--classes", str(classes_path)]
    params = StdioServerParameters(command=sys.executable, args=cmd[1:])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            doc = await session.call_tool("read_external_doc", {"path": "/tmp/x.md"})
            echo = await session.call_tool("echo", {"text": "hello-taint"})
            return names, doc.content[0].text, echo.content[0].text


def _entries(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def test_source_marking_in_flow_log(tmp_path: Path) -> None:
    flow_log = tmp_path / "flow.jsonl"
    taint_log = tmp_path / "taint.jsonl"
    names, doc_text, echo_text = asyncio.run(_run_proxy(flow_log, taint_log))

    assert names == ["echo", "read_external_doc", "send_email"]
    assert doc_text == DOC_TEXT
    assert echo_text == "hello-taint"

    entries = _entries(flow_log)
    calls = [e for e in entries if e["method"] == "tools/call" and e["direction"] == "front_request"]
    assert len(calls) == 2, "两个调用都应被拦截并记录"

    doc_call = next(e for e in calls if e["payload"]["name"] == "read_external_doc")
    assert doc_call["payload"]["class"] == "source"
    assert doc_call["payload"]["call_id"].startswith("t-")

    echo_call = next(e for e in calls if e["payload"]["name"] == "echo")
    assert echo_call["payload"]["class"] == "neutral"

    marks = [e for e in entries if e["method"] == "source_marked"]
    assert len(marks) == 1, "仅 SOURCE 工具产生污点记录"
    payload = marks[0]["payload"]
    assert payload["call_id"] == doc_call["payload"]["call_id"]
    assert payload["tool"] == "read_external_doc"
    assert payload["raw_text"] == DOC_TEXT, "日志须含完整污点源数据（原始文本）"
    assert payload["chunk_count"] >= 1
    assert payload["chunks"], "日志须含完整污点源数据（分块）"
    assert "".join(payload["chunks"]) != "" and payload["chunks"][0] == normalize(DOC_TEXT)

    taint_entries = _entries(taint_log)
    assert len(taint_entries) == 1
    assert taint_entries[0]["call_id"] == doc_call["payload"]["call_id"]
    assert taint_entries[0]["chunks"] == payload["chunks"]


def test_class_override(tmp_path: Path) -> None:
    flow_log = tmp_path / "flow2.jsonl"
    asyncio.run(
        _run_proxy(flow_log, None, classes={"echo": "sink", "read_external_doc": "neutral"})
    )
    entries = _entries(flow_log)
    calls = [e for e in entries if e["method"] == "tools/call" and e["direction"] == "front_request"]
    classes = {e["payload"]["name"]: e["payload"]["class"] for e in calls}
    assert classes == {"read_external_doc": "neutral", "echo": "sink"}
    assert not [e for e in entries if e["method"] == "source_marked"], (
        "被覆盖为 neutral 后不再产生污点记录"
    )
