"""子串层传播检测（规格 §5）：SINK 调用参数命中任一污点块即产生 TaintEdge。

流程：递归提取参数字符串（带字段路径）→ §4 归一化 → 与 TaintStore 全量块做
包含检测。归一化后长度低于 MIN_MATCH 的值直接跳过（§5 阈值）。
复杂度 O(参数串 × 块数)，D9 实测性能、必要时加索引。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chunk import MIN_MATCH
from .normalize import normalize
from .store import TaintRecord, TaintStore


@dataclass
class TaintHit:
    source_call_id: str
    source_tool: str
    sink_field: str
    matched_snippet: str
    chunk: str

    @property
    def layer(self) -> str:
        return "substring"


def extract_strings(value: Any, path: str = "args") -> list[tuple[str, str]]:
    """递归提取所有字符串值，path 形如 args.body、args.recipients[0]。"""
    out: list[tuple[str, str]] = []
    if isinstance(value, str):
        out.append((path, value))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(extract_strings(v, f"{path}.{k}"))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            out.extend(extract_strings(v, f"{path}[{i}]"))
    return out


def detect_taint(arguments: dict[str, Any], store: TaintStore) -> list[TaintHit]:
    hits: list[TaintHit] = []
    for path, value in extract_strings(arguments):
        norm = normalize(value)
        if len(norm) < MIN_MATCH:
            continue
        for rec in store:
            for chunk in rec.chunks:
                idx = norm.find(chunk)
                if idx != -1:
                    hits.append(
                        TaintHit(
                            source_call_id=rec.call_id,
                            source_tool=rec.tool,
                            sink_field=path,
                            matched_snippet=value[idx : idx + len(chunk)],
                            chunk=chunk,
                        )
                    )
    return hits
