"""运行时接入自己的工具面（公网安全版）。

用户上传的是 **模板 + 工具清单**：选一个平台内置模板，声明工具分类 / sink /
载体工具，平台用同一套攻击引擎、污点代理和确定性 oracle 跑一组攻击。

安全模型（与早期"上传任意命令"版本的根本区别）：
- **平台只执行自己的代码**。backend 固定为 `python -m range.backend --profile <模板>`
  ，命令字符串不再由用户上传，杜绝任意命令执行 / 反弹 shell。
- 模板限定为无描述面的内置 profile（t1/t2/t5）；A3 需要改写 MCP server 描述，
  不在上传能力内。
- 用户只能在模板暴露的工具集里改分类与 sink，改不出新的工具面。

因此该能力可以在公网开启：默认仍关闭（MCPSENTRY_ALLOW_CUSTOM=1），
compose 里显式打开即可，风险等同于内置靶场。
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

# 每个公网可开放模板 → 该内置 profile 暴露的工具与默认分类。
# 用户提交的 tool_classes 只能从这些 key 里选，不能再造工具。
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
    template: str = Field(default="t1", description="平台内置模板 id：t1 / t2 / t5")
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
    """默认拒绝：公网实例由 compose 显式打开开关后才可用。"""
    if os.environ.get("MCPSENTRY_ALLOW_CUSTOM", "0") != "1":
        raise PermissionError(
            "自定义工具面接入未启用。在服务端设置 MCPSENTRY_ALLOW_CUSTOM=1 后重启平台。"
        )


def validate(body: CustomRunBody) -> None:
    if not body.confirm:
        raise ValueError("自定义运行需要 confirm=true（确认使用平台内置工具面）")
    if body.template not in TEMPLATE_TOOLS:
        raise ValueError(
            f"template 必须是 {sorted(TEMPLATE_TOOLS)} 之一（收到 {body.template!r}）"
        )
    if body.attack_class not in _ALLOWED_ATTACKS:
        raise ValueError(
            f"自定义接入暂不支持 {body.attack_class}；可用：{sorted(_ALLOWED_ATTACKS)}"
            "（A3 需要改写 MCP server 的工具描述，当前不在能力内）"
        )
    if body.defense not in ("off", "block", "alert"):
        raise ValueError("defense 只能是 off / block / alert")

    allowed = TEMPLATE_TOOLS[body.template]
    unknown = [t for t in body.tool_classes if t not in allowed]
    if unknown:
        raise ValueError(
            f"模板 {body.template} 不含工具 {unknown}；可用工具：{sorted(allowed)}"
            "（平台只执行自己的内置 MCP server，不能新增工具）"
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
    seed = json.dumps(
        {
            "name": body.name,
            "template": body.template,
            "tool_classes": body.tool_classes,
            "sinks": sorted(body.sinks),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return "C-" + hashlib.sha256(seed).hexdigest()[:8].upper()


def _backend_command(template: str) -> tuple[str, ...]:
    """执行体由平台写死：只跑内置 range.backend，不接受用户传入的命令。"""
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
    entry = TargetSpecEntry(
        id=target_id(body),
        name=body.name,
        profile=body.template,
        port=0,
        vulnerability="运行时接入的自定义工具分类",
        mcp_servers=(body.template,),
        tool_classes=dict(body.tool_classes),
        carrier="doc",
        carrier_tool=body.carrier_tool,
        sinks=tuple(body.sinks),
        hardened=body.hardened,
        applicable=NO_DESC_SURFACE,
        description=body.description or "用户声明工具分类的自定义工具面",
        backend_command=_backend_command(body.template),
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
    """前端「填入样例」：t1 模板的默认工具清单，点一下即可跑通。"""
    return {
        "name": "示例工具面",
        "template": "t1",
        "tool_classes": dict(TEMPLATE_TOOLS["t1"]),
        "sinks": ["send_email"],
        "carrier_tool": "read_doc",
        "attack_class": AttackClass.A2_INDIRECT_TOOL_RESULT.value,
        "seed": 42,
        "defense": "block",
        "description": "自检示例：t1 工具面，验证模板 + 工具清单链路",
        "note": "接入自检",
        "confirm": True,
    }
