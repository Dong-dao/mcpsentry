"""运行时接入自己的 MCP 工具链。

用户上传的是 **stdio MCP server 命令 + 工具分类 + sink 列表**，不是任意远程 Agent：
受害者仍是我们确定性的 RangeVictim，所以四类攻击里的 A1/A2/A4 能完整跑通，
判定链、污点证据和 replay_hash 与内置靶标完全同一套。

安全边界：
- 命令在平台所在主机上执行，默认关闭；置 `MCPSENTRY_ALLOW_CUSTOM=1` 才开放。
- 只允许 python/python3 解释器开头的命令（可带任意脚本参数），且参数长度受限。
  公网部署请保持关闭，或放到只接受可信内网请求的实例上。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from engine.contracts import AttackClass
from range.specs import NO_DESC_SURFACE, TargetSpecEntry, register_custom

_ALLOWED_ATTACKS = set(NO_DESC_SURFACE)
_ALLOWED_PY = {"python", "python3", "py", os.path.basename(sys.executable).lower()}


class CustomRunBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    command: list[str] = Field(min_length=1, max_length=20)
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


def ensure_enabled() -> None:
    """默认拒绝：上传配置 = 在主机上跑用户给的命令，必须显式打开。"""
    if os.environ.get("MCPSENTRY_ALLOW_CUSTOM", "0") != "1":
        raise PermissionError(
            "自定义 MCP 接入未启用。在服务端设置 MCPSENTRY_ALLOW_CUSTOM=1 后重启平台；"
            "该开关会在本机执行上传的命令，公网实例请谨慎开启。"
        )


def validate(body: CustomRunBody) -> None:
    if not body.confirm:
        raise ValueError("自定义运行需要 confirm=true（确认命令将在平台主机执行）")
    if body.attack_class not in _ALLOWED_ATTACKS:
        raise ValueError(
            f"自定义接入暂不支持 {body.attack_class}；可用：{sorted(_ALLOWED_ATTACKS)}"
            "（A3 需要改写 MCP server 的工具描述，当前不在上传配置能力内）"
        )
    if body.defense not in ("off", "block", "alert"):
        raise ValueError("defense 只能是 off / block / alert")
    exe = os.path.basename(body.command[0]).lower()
    if exe not in _ALLOWED_PY:
        raise ValueError(
            f"命令必须以 python/python3 开头（收到 {body.command[0]!r}）；"
            "这是防止上传配置任意执行本机程序的白名单"
        )
    for arg in body.command:
        if not arg or "\x00" in arg or len(arg) > 500:
            raise ValueError("command 参数不能为空、不能含 NUL、且单条不超过 500 字符")
    unknown = [s for s in body.sinks if body.tool_classes.get(s) != "sink"]
    if unknown:
        raise ValueError(f"sinks 必须同时标注为 sink：{unknown}")
    sources = [t for t, c in body.tool_classes.items() if c == "source"]
    if not sources:
        raise ValueError("至少要把一个工具标注为 source，污点层才有输入")
    if body.attack_class != "A1_direct_injection" and body.carrier_tool not in body.tool_classes:
        raise ValueError(f"carrier_tool {body.carrier_tool!r} 不在 tool_classes 中")
    if len(body.description) > 500 or len(body.note) > 200:
        raise ValueError("description 最多 500 字符，note 最多 200 字符")


def target_id(body: CustomRunBody) -> str:
    seed = json.dumps(
        {"name": body.name, "command": body.command}, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return "C-" + hashlib.sha256(seed).hexdigest()[:8].upper()


def build_entry(body: CustomRunBody) -> TargetSpecEntry:
    validate(body)
    entry = TargetSpecEntry(
        id=target_id(body),
        name=body.name,
        profile="custom",
        port=0,
        vulnerability="运行时接入的自定义 MCP 工具链",
        mcp_servers=(body.name,),
        tool_classes=dict(body.tool_classes),
        carrier="doc",
        carrier_tool=body.carrier_tool,
        sinks=tuple(body.sinks),
        hardened=body.hardened,
        applicable=NO_DESC_SURFACE,
        description=body.description or "用户上传配置接入的 MCP server",
        backend_command=tuple(body.command),
    )
    return register_custom(entry)


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
    """本地自检用：直接用内置 range.backend 当「用户自己的 MCP server」。"""
    return {
        "name": "示例 MCP 工具链",
        "command": [
            sys.executable,
            "-m",
            "range.backend",
            "--profile",
            "t1",
            "--workdir",
            "{workdir}",
        ],
        "tool_classes": {"read_doc": "source", "send_email": "sink"},
        "sinks": ["send_email"],
        "carrier_tool": "read_doc",
        "attack_class": AttackClass.A2_INDIRECT_TOOL_RESULT.value,
        "seed": 42,
        "defense": "block",
        "description": "自检示例：与内置 T1 同工具面，验证上传配置链路",
        "note": "本地自检",
        "confirm": True,
    }
