"""stdio MCP 透明代理核心。

对前端 Agent 表现为 MCP 服务器；内部 spawn 真实后端 MCP 服务器（stdio 子进程），
拦截并转发 tools/list 与 tools/call，全程写入流量日志。

D2 验收：透明转发不破坏正常调用（见 tests/test_proxy_transparent.py）。
D3：tools/call 拦截——每次调用分配 call_id 并记录工具分类，SOURCE 工具返回值
    归一化+分块存入 TaintStore，flow log 写 taint/source_marked（完整污点源数据）。
D4+ 挂接点：handle_call_tool 内做子串层传播检测与 sink 策略；handle_list_tools 内做描述扫描。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ..taint import ToolClass, TaintStore, classify_tool
from .flow_log import FlowLogger


def _extract_text(content: list[Any]) -> str:
    return " ".join(c.text for c in content if isinstance(c, TextContent) and c.text)


async def run_proxy(
    backend_cmd: list[str],
    backend_env: dict[str, str] | None = None,
    log_path: str | None = None,
    taint_log_path: str | None = None,
    tool_classes: dict[str, str] | None = None,
    name: str = "mcpsentry-proxy",
) -> None:
    logger = FlowLogger(log_path)
    taint_store = TaintStore(taint_log_path)
    server = Server(name)
    backend_params = StdioServerParameters(
        command=backend_cmd[0], args=backend_cmd[1:], env=backend_env
    )

    async with AsyncExitStack() as stack:
        backend_read, backend_write = await stack.enter_async_context(
            stdio_client(backend_params)
        )
        backend_session = await stack.enter_async_context(
            ClientSession(backend_read, backend_write)
        )
        await backend_session.initialize()
        logger.log("backend", "initialize", {"status": "ok"})

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            logger.log("front_request", "tools/list", {})
            result = await backend_session.list_tools()
            tools = list(result.tools)
            logger.log(
                "backend_response",
                "tools/list",
                {"tools": [t.model_dump() for t in tools]},
            )
            return tools

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
            call_id = f"t-{uuid.uuid4().hex[:12]}"
            tool_class = classify_tool(name, tool_classes)
            logger.log(
                "front_request",
                "tools/call",
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments,
                    "class": tool_class.value,
                },
            )
            result = await backend_session.call_tool(name, arguments)
            logger.log(
                "backend_response",
                "tools/call",
                {
                    "call_id": call_id,
                    "name": name,
                    "isError": result.isError,
                    "content": [c.model_dump() for c in result.content],
                },
            )
            if result.isError:
                text = "; ".join(
                    getattr(c, "text", "") for c in result.content if hasattr(c, "text")
                )
                raise RuntimeError(f"backend tool error: {text or name}")
            if tool_class is ToolClass.SOURCE:
                rec = taint_store.record(
                    call_id, name, _extract_text(result.content)
                )
                logger.log(
                    "taint",
                    "source_marked",
                    {
                        "call_id": rec.call_id,
                        "tool": rec.tool,
                        "ts_ms": rec.ts_ms,
                        "chunk_count": len(rec.chunks),
                        "raw_text": rec.raw_text,
                        "chunks": rec.chunks,
                    },
                )
            return list(result.content)

        front_read, front_write = await stack.enter_async_context(stdio_server())
        await server.run(front_read, front_write, server.create_initialization_options())
        logger.log("session", "closed", {})
