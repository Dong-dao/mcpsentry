"""stdio MCP 透明代理核心。

对前端 Agent 表现为 MCP 服务器；内部 spawn 真实后端 MCP 服务器（stdio 子进程），
拦截并转发 tools/list 与 tools/call，全程写入流量日志。

D2 验收：透明转发不破坏正常调用（见 tests/test_proxy_transparent.py）。
D3：tools/call 拦截——每次调用分配 call_id 并记录工具分类，SOURCE 工具返回值
    归一化+分块存入 TaintStore，flow log 写 taint/source_marked（完整污点源数据）。
D4：污点传播——SINK 调用先跑子串层检测；命中按 policy 处理（alert 记边放行，
    block 拒绝调用不触达后端）；首次 SOURCE 读取后进入能力降级（alert 升级为 block）。
D5：tools/list 跑描述投毒扫描（poison_score≥2 高危）+ rug-pull 哈希钉扎（基线
    之后的描述变更记 RUG_PULL_SUSPECT 并 block 该工具）；子串层未命中且已降级时，
    SINK 调用走语义层复核（influenced∧confidence≥0.8 → 拦截，单会话 20 次上限）。
D12：block 档下，描述扫描高危的工具同样在调用时被拒（desc_block）——D9 实跑
    暴露的 T3 盲区（基线即投毒、无漂移可比对，扫描只记录不拦截）；alert 档仍只记录。
"""

from __future__ import annotations

import os
import uuid
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ..contracts import PolicyMode
from ..taint import (
    K,
    SemanticJudge,
    TaintStore,
    ToolClass,
    RugPullPinner,
    classify_tool,
    detect_taint,
    scan_description,
)
from .flow_log import FlowLogger


def _extract_text(content: list[Any]) -> str:
    return " ".join(c.text for c in content if isinstance(c, TextContent) and c.text)


async def run_proxy(
    backend_cmd: list[str],
    backend_env: dict[str, str] | None = None,
    log_path: str | None = None,
    taint_log_path: str | None = None,
    tool_classes: dict[str, str] | None = None,
    policy: str = "block",
    downgrade_on_untrusted: bool = True,
    semantic_judge: SemanticJudge | None = None,
    seed: int | None = None,
    stdin: Any = None,
    stdout: Any = None,
    name: str = "mcpsentry-proxy",
) -> None:
    logger = FlowLogger(log_path)
    taint_store = TaintStore(taint_log_path)
    policy_mode = PolicyMode(policy)
    downgraded = False
    pinner = RugPullPinner()
    rugpull_blocked: set[str] = set()
    desc_highrisk: set[str] = set()
    cap_logged = False
    call_seq = 0
    if semantic_judge is None:
        if os.environ.get("DASHSCOPE_API_KEY"):
            semantic_judge = SemanticJudge()
        else:
            logger.log("semantic", "disabled", {"reason": "DASHSCOPE_API_KEY not set"})
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
            nonlocal desc_highrisk
            logger.log("front_request", "tools/list", {})
            result = await backend_session.list_tools()
            tools = list(result.tools)
            logger.log(
                "backend_response",
                "tools/list",
                {"tools": [t.model_dump() for t in tools]},
            )

            for tool in tools:
                scan = scan_description(tool.name, tool.description or "")
                if scan.rules:
                    logger.log(
                        "desc",
                        "scan",
                        {
                            "tool": scan.tool,
                            "score": scan.score,
                            "rules": scan.rules,
                            "high_risk": scan.high_risk,
                        },
                    )
                if scan.high_risk:
                    desc_highrisk.add(tool.name)

            events, established = pinner.check(tools)
            if established:
                logger.log("rugpull", "baseline", {"tools": sorted(t.name for t in tools)})
            for event in events:
                rugpull_blocked.add(event.tool)
                logger.log(
                    "rugpull",
                    "suspect",
                    {
                        "tool": event.tool,
                        "status": event.status,
                        "old_hash": event.old_hash,
                        "new_hash": event.new_hash,
                        "diff": event.diff,
                    },
                )
            return tools

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
            nonlocal downgraded, cap_logged, call_seq
            # seed 模式下 call_id 用确定性序号（基准回放一致性 §7 的前提）
            if seed is None:
                call_id = f"t-{uuid.uuid4().hex[:12]}"
            else:
                call_id = f"t-{call_seq:012d}"
                call_seq += 1
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

            if name in rugpull_blocked:
                logger.log(
                    "taint",
                    "rugpull_block",
                    {"call_id": call_id, "tool": name, "blocked": True},
                )
                raise RuntimeError(
                    f"policy_blocked: rug_pull_detected on tool {name} "
                    f"(description changed after baseline)"
                )

            if name in desc_highrisk and policy_mode is PolicyMode.BLOCK:
                logger.log(
                    "taint",
                    "desc_block",
                    {"call_id": call_id, "tool": name, "blocked": True},
                )
                raise RuntimeError(
                    f"policy_blocked: poisoned description detected on tool {name}"
                )

            if tool_class is ToolClass.SINK:
                hits = detect_taint(arguments, taint_store)
                # 能力降级：首次读取不可信内容后，alert 档也升级为 block
                blocked = bool(hits) and (
                    policy_mode is PolicyMode.BLOCK
                    or (downgraded and policy_mode is PolicyMode.ALERT)
                )
                for hit in hits:
                    logger.log(
                        "taint",
                        "edge",
                        {
                            "call_id": call_id,
                            "sink_tool": name,
                            "sink_field": hit.sink_field,
                            "source_call_id": hit.source_call_id,
                            "source_tool": hit.source_tool,
                            "layer": hit.layer,
                            "blocked": blocked,
                            "matched_snippet": hit.matched_snippet,
                            "downgraded": downgraded,
                        },
                    )
                if blocked:
                    hit = hits[0]
                    raise RuntimeError(
                        f"policy_blocked: tainted content from "
                        f"{hit.source_tool} ({hit.source_call_id}) reached "
                        f"{name}.{hit.sink_field}"
                    )

                if not hits and downgraded and semantic_judge is not None:
                    if semantic_judge.exhausted and not cap_logged:
                        cap_logged = True
                        logger.log("semantic", "cap_reached", {"max_calls": semantic_judge._max_calls})
                    recent = list(taint_store)[-K:]
                    verdict = await semantic_judge.judge(name, arguments, recent)
                    logger.log(
                        "semantic",
                        "verdict",
                        {
                            "call_id": call_id,
                            "influenced": verdict.influenced,
                            "confidence": verdict.confidence,
                            "reason": verdict.reason,
                        },
                    )
                    if verdict.influenced and verdict.confidence >= 0.8:
                        provenance = recent[-1] if recent else None
                        logger.log(
                            "taint",
                            "edge",
                            {
                                "call_id": call_id,
                                "sink_tool": name,
                                "sink_field": "",
                                "source_call_id": provenance.call_id if provenance else "",
                                "source_tool": provenance.tool if provenance else "",
                                "layer": "semantic",
                                "blocked": True,
                                "matched_snippet": "",
                                "downgraded": True,
                                "reason": verdict.reason,
                                "confidence": verdict.confidence,
                            },
                        )
                        raise RuntimeError(
                            f"policy_blocked: semantic layer flagged tainted influence "
                            f"on {name}: {verdict.reason}"
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
                if downgrade_on_untrusted and not downgraded:
                    downgraded = True
                    logger.log("taint", "downgraded", {"call_id": rec.call_id})
            return list(result.content)

        front_read, front_write = await stack.enter_async_context(
            stdio_server(stdin=stdin, stdout=stdout)
        )
        await server.run(front_read, front_write, server.create_initialization_options())
        logger.log("session", "closed", {})
