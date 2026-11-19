"""D2 验收测试：代理透明转发不破坏正常调用，且全流量日志完整。

以本测试进程为"前端 Agent"，经 stdio 连接代理；代理 spawn fake_backend。
断言：工具清单透传、echo/add 结果透传、日志含双向记录。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "fake_backend.py"


async def _client_roundtrip(log_path: Path) -> tuple[list[str], str, str]:
    backend = [sys.executable, str(FIXTURE)]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "engine.proxy", "--backend", json.dumps(backend), "--log", str(log_path)],
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            echo = await session.call_tool("echo", {"text": "hello-proxy"})
            add = await session.call_tool("add", {"a": 2, "b": 3})
            return names, echo.content[0].text, add.content[0].text


def test_transparent_forwarding(tmp_path: Path) -> None:
    log_path = tmp_path / "flow.jsonl"
    names, echo_text, add_text = asyncio.run(_client_roundtrip(log_path))

    assert names == ["add", "echo"]
    assert echo_text == "hello-proxy"
    assert add_text == "5"

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "flow log must not be empty"
    entries = [json.loads(line) for line in lines]

    methods = {(e["direction"], e["method"]) for e in entries}
    assert ("front_request", "tools/list") in methods
    assert ("front_request", "tools/call") in methods
    assert ("backend_response", "tools/list") in methods
    assert ("backend_response", "tools/call") in methods

    call_logs = [e for e in entries if e["method"] == "tools/call" and e["direction"] == "backend_response"]
    assert call_logs, "backend tools/call response must be logged"
    payload = call_logs[0]["payload"]
    assert payload["isError"] is False
