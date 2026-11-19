"""测试用最小 stdio MCP 后端：echo / add 两个工具（D2 透明转发验收）。"""

from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

ECHO_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
ADD_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
    "required": ["a", "b"],
}


def main() -> None:
    server = Server("fake-backend")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(name="echo", description="Echo text back", inputSchema=ECHO_SCHEMA),
            Tool(name="add", description="Add two numbers", inputSchema=ADD_SCHEMA),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        if name == "echo":
            return [TextContent(type="text", text=str(arguments.get("text", "")))]
        if name == "add":
            total = int(arguments.get("a", 0)) + int(arguments.get("b", 0))
            return [TextContent(type="text", text=str(total))]
        raise ValueError(f"unknown tool: {name}")

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
