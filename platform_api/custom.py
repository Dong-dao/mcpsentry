"""运行时接入自己的 MCP 工具面（白名单 + 显式开关）。

两种模式：
- **不传 command**：模板 + 工具清单；执行体固定为
  `python -m range.backend --profile <模板> --workdir <隔离目录>`（6113a0a 行为）。
- **传 command**：用户上传的 stdio MCP server 命令；解释器白名单为
  python / python3 / 当前 sys.executable，参数非空、无 NUL、单参数 ≤ 500 字符。

安全边界：命令在平台所在主机执行，默认关闭；必须显式设置
`MCPSENTRY_ALLOW_CUSTOM=1` 才开放（模板模式同样受该开关约束）。
探测接口 `POST /api/custom/probe` 只跑 initialize + tools/list，
不执行工具调用；失败详情一律用通用中文文案，不回显 token / IP / 命令细节。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

from engine.contracts import AttackClass
from range.specs import NO_DESC_SURFACE, TargetSpecEntry, register_custom

_ALLOWED_ATTACKS = set(NO_DESC_SURFACE)
_ALLOWED_DEFENSES = ("off", "block", "alert", "strict")
_ALLOWED_PY = {"python", "python3"}
_MAX_COMMAND_ARGS = 20
_MAX_ARG_CHARS = 500
PROBE_TIMEOUT_SECONDS = 15.0

# 每个公网可开放模板 → 该内置 profile 暴露的工具与默认分类。
# 仅在「不传 command」时约束用户声明的工具 key。
TEMPLATE_TOOLS: dict[str, dict[str, str]] = {
    "t1": {"read_doc": "source", "send_email": "sink"},
    "t2": {
        "web_fetch": "source",
        "read_doc": "source",
        "write_file": "sink",
        "send_email": "sink",
    },
    "t5": {"read_doc": "source", "send_email": "sink"},
}


class CustomRunBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    template: str = Field(default="t1", description="模板模式的内置 profile：t1 / t2 / t5")
    command: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=_MAX_COMMAND_ARGS,
        description="用户自己的 stdio MCP server 命令；不传则走内置模板执行体",
    )
    tool_classes: dict[str, Literal["source", "sink", "neutral"]]
    sinks: list[str] = Field(min_length=1)
    carrier_tool: str = "read_doc"
    attack_class: str = "A2_indirect_tool_result"
    seed: int = 42
    defense: str = "block"
    hardened: bool = False
    description: str = ""
    note: str = ""
    confirm: bool = False


class CustomProbeBody(BaseModel):
    command: list[str] = Field(min_length=1, max_length=_MAX_COMMAND_ARGS)
    confirm: bool = False


def ensure_enabled() -> None:
    """默认拒绝：上传命令 = 在主机上跑用户给的程序，必须显式打开。"""
    if os.environ.get("MCPSENTRY_ALLOW_CUSTOM", "0") != "1":
        raise PermissionError(
            "自定义 MCP 接入未启用。在服务端设置 MCPSENTRY_ALLOW_CUSTOM=1 后重启平台。"
        )


def _is_allowed_interpreter(token: str) -> bool:
    if token.lower() in _ALLOWED_PY:
        return True
    try:
        return os.path.normcase(os.path.abspath(token)) == os.path.normcase(
            os.path.abspath(sys.executable)
        )
    except (OSError, ValueError):
        return False


def validate_command(command: list[str] | None) -> None:
    """probe 与 runs 共用的命令白名单；错误文案不回显用户参数。"""
    if command is None:
        return
    if not 1 <= len(command) <= _MAX_COMMAND_ARGS:
        raise ValueError("command 需要 1–20 个参数")
    if not _is_allowed_interpreter(command[0]):
        raise ValueError(
            "command 必须以 python / python3 或当前解释器开头（其余解释器禁止）"
        )
    for arg in command:
        if not arg or "\x00" in arg or len(arg) > _MAX_ARG_CHARS:
            raise ValueError("command 参数不能为空、不能含 NUL、且单条不超过 500 字符")


def validate(body: CustomRunBody) -> None:
    if not body.confirm:
        raise ValueError("自定义运行需要 confirm=true（确认配置将在平台主机执行）")
    if body.attack_class not in _ALLOWED_ATTACKS:
        raise ValueError(
            f"自定义接入暂不支持 {body.attack_class}；可用：{sorted(_ALLOWED_ATTACKS)}"
            "（A3 需要改写 MCP server 的工具描述，当前不在能力内）"
        )
    if body.defense not in _ALLOWED_DEFENSES:
        raise ValueError("defense 只能是 off / block / alert / strict")

    validate_command(body.command)
    if body.command is None:
        if body.template not in TEMPLATE_TOOLS:
            raise ValueError(
                f"template 必须是 {sorted(TEMPLATE_TOOLS)} 之一（收到 {body.template!r}）"
            )
        allowed = TEMPLATE_TOOLS[body.template]
        unknown = [t for t in body.tool_classes if t not in allowed]
        if unknown:
            raise ValueError(
                f"模板 {body.template} 不含工具 {unknown}；可用工具：{sorted(allowed)}"
                "（模板模式只执行自己的内置 MCP server，不能新增工具）"
            )

    bad_sinks = [s for s in body.sinks if body.tool_classes.get(s) != "sink"]
    if bad_sinks:
        raise ValueError(f"sinks 必须同时标注为 sink：{bad_sinks}")
    sources = [t for t, c in body.tool_classes.items() if c == "source"]
    if not sources:
        raise ValueError("至少要把一个工具标注为 source，污点层才有输入")
    if body.attack_class != "A1_direct_injection" and body.carrier_tool not in body.tool_classes:
        raise ValueError(f"carrier_tool {body.carrier_tool!r} 不在 tool_classes 中")
    if len(body.description) > 500 or len(body.note) > 200:
        raise ValueError("description 最多 500 字符，note 最多 200 字符")


def target_id(body: CustomRunBody) -> str:
    seed: dict[str, Any] = {
        "name": body.name,
        "template": body.template,
        "tool_classes": body.tool_classes,
        "sinks": sorted(body.sinks),
    }
    if body.command is not None:
        seed["command"] = body.command
    return "C-" + hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8].upper()


def _backend_command(template: str) -> tuple[str, ...]:
    """模板模式的执行体由平台写死，不接受该模式传入的命令。"""
    return (
        sys.executable,
        "-m",
        "range.backend",
        "--profile",
        template,
        "--workdir",
        "{workdir}",
    )


def build_entry(body: CustomRunBody) -> TargetSpecEntry:
    validate(body)
    custom = body.command is not None
    entry = TargetSpecEntry(
        id=target_id(body),
        name=body.name,
        profile="custom" if custom else body.template,
        port=0,
        vulnerability=(
            "运行时接入的自定义 MCP 工具链" if custom else "运行时接入的自定义工具分类"
        ),
        mcp_servers=(body.name,) if custom else (body.template,),
        tool_classes=dict(body.tool_classes),
        carrier="doc",
        carrier_tool=body.carrier_tool,
        sinks=tuple(body.sinks),
        hardened=body.hardened,
        applicable=NO_DESC_SURFACE,
        description=(
            body.description
            or ("用户上传命令接入的 MCP server" if custom else "用户声明工具分类的自定义工具面")
        ),
        backend_command=tuple(body.command) if custom else _backend_command(body.template),
    )
    return register_custom(entry)


async def probe_command(body: CustomProbeBody) -> dict[str, Any]:
    """spawn 用户 MCP server，跑 initialize + tools/list；{workdir} 指向临时目录。

    异常映射由 app 层负责：ValueError→422、TimeoutError→504、RuntimeError→502。
    """
    if not body.confirm:
        raise ValueError("MCP 工具探测需要 confirm=true（确认命令将在平台主机执行）")
    validate_command(body.command)
    assert body.command is not None  # validate_command + pydantic 已保证

    with tempfile.TemporaryDirectory(prefix="mcpsentry-probe-") as workdir:
        argv = [part.replace("{workdir}", workdir) for part in body.command]
        params = StdioServerParameters(command=argv[0], args=argv[1:])
        started = time.perf_counter()

        async def _list_tools() -> list[dict[str, Any]]:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema,
                        }
                        for tool in result.tools
                    ]

        try:
            tools = await asyncio.wait_for(_list_tools(), timeout=PROBE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            raise TimeoutError("MCP tools/list 探测超时，已终止子进程") from None
        except Exception:
            # 不回显异常文本：其中可能含用户命令、本机路径或 token
            raise RuntimeError("MCP server 无法初始化或 tools/list 探测失败（细节已隐藏）") from None
        return {
            "ok": True,
            "tools": tools,
            "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        }


def run_id(entry: TargetSpecEntry, body: CustomRunBody) -> str:
    cls = body.attack_class.split("_", 1)[0]
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    return f"c-{entry.id.lower()}-{cls}-s{body.seed}-{body.defense}-{stamp}"


def request_payload(entry: TargetSpecEntry, body: CustomRunBody) -> dict[str, Any]:
    """与 RunRequest 字段一致，供 history.mark_queued 使用。"""
    return {
        "target": entry.id,
        "attack_class": body.attack_class,
        "seed": body.seed,
        "defense": body.defense,
        "paraphrase": False,
        "semantic": False,
        "note": body.note or f"自定义接入：{body.name}",
    }


def example_body() -> dict[str, Any]:
    """前端「填入样例」：可提交的命令模式配置，等价于内置 t1 工具面。"""
    return {
        "name": "示例 MCP 工具链",
        "template": "t1",
        "command": [
            sys.executable,
            "-m",
            "range.backend",
            "--profile",
            "t1",
            "--workdir",
            "{workdir}",
        ],
        "tool_classes": dict(TEMPLATE_TOOLS["t1"]),
        "sinks": ["send_email"],
        "carrier_tool": "read_doc",
        "attack_class": AttackClass.A2_INDIRECT_TOOL_RESULT.value,
        "seed": 42,
        "defense": "block",
        "description": "自检示例：与内置 T1 同工具面，验证命令上传链路",
        "note": "本地自检",
        "confirm": True,
    }
