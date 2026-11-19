"""工具分类（规格 §2）：SOURCE 返回不可信内容，SINK 有副作用，其余 NEUTRAL。

默认分类表可被 RunConfig（target 自定义工具集）覆盖：overrides 形如
{"tool_name": "source|sink|neutral"}，非法值抛错——分类是安全判定输入，不能静默吞掉。
"""

from __future__ import annotations

from enum import Enum


class ToolClass(str, Enum):
    SOURCE = "source"
    SINK = "sink"
    NEUTRAL = "neutral"


DEFAULT_SOURCES = {"web_fetch", "read_external_doc", "mail_read", "search_web"}
DEFAULT_SINKS = {"send_email", "http_post", "write_file", "execute", "delete_file"}


def classify_tool(name: str, overrides: dict[str, str] | None = None) -> ToolClass:
    if overrides and name in overrides:
        try:
            return ToolClass(overrides[name])
        except ValueError:
            raise ValueError(
                f"invalid tool class {overrides[name]!r} for {name!r}; "
                f"expected one of {[c.value for c in ToolClass]}"
            ) from None
    if name in DEFAULT_SOURCES:
        return ToolClass.SOURCE
    if name in DEFAULT_SINKS:
        return ToolClass.SINK
    return ToolClass.NEUTRAL
