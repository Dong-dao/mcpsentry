"""rug-pull 哈希钉扎协议（规格 §9）。

无批准事件的会话（自动接入）以首次 tools/list 为基线：记录每条工具描述归一化
文本的 sha256。此后每次列表比对；差异 → RUG_PULL_SUSPECT（含 diff 摘要），代理侧
默认 block 该工具的后续调用。归一化后再哈希，因此大小写/空白抖动不触发告警。
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass

from .normalize import normalize


def description_hash(description: str) -> str:
    return hashlib.sha256(normalize(description).encode("utf-8")).hexdigest()


@dataclass
class RugPullEvent:
    tool: str
    status: str  # changed | new_tool | removed
    old_hash: str | None = None
    new_hash: str | None = None
    diff: str = ""


class RugPullPinner:
    def __init__(self) -> None:
        self._baseline: dict[str, tuple[str, str]] | None = None  # name -> (hash, raw desc)

    @property
    def baseline_set(self) -> bool:
        return self._baseline is not None

    def check(self, tools: list) -> tuple[list[RugPullEvent], bool]:
        """比对当前工具清单；返回 (事件列表, 本次是否建立基线)。"""
        hashes = {t.name: description_hash(t.description or "") for t in tools}
        descs = {t.name: t.description or "" for t in tools}

        if self._baseline is None:
            self._baseline = {name: (h, descs[name]) for name, h in hashes.items()}
            return [], True

        events: list[RugPullEvent] = []
        for name, h in hashes.items():
            if name not in self._baseline:
                events.append(RugPullEvent(name, "new_tool", None, h, "tool appeared after baseline"))
                # 告警一次后钉住当前状态，后续按哈希比对
                self._baseline[name] = (h, descs[name])
                continue
            base_hash, base_desc = self._baseline[name]
            if h != base_hash:
                events.append(
                    RugPullEvent(name, "changed", base_hash, h, _diff_summary(base_desc, descs[name]))
                )
        for name in list(self._baseline):
            if name not in hashes:
                events.append(
                    RugPullEvent(name, "removed", self._baseline[name][0], None, "tool removed after baseline")
                )
                # 取消钉扎：该工具若再次出现会重新告警
                del self._baseline[name]
        return events, False


def _diff_summary(old: str, new: str) -> str:
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1)
    return "\n".join(list(diff)[:12])
