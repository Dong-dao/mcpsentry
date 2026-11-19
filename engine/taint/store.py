"""会话级 TaintStore（规格 §3）：SOURCE 工具返回值归一化+分块落库。

内存 dict 为主（子串层查表），JSONL 落盘用于轨迹审计（oracle 读取来源之一）。
D4 将在 SINK 调用到达时对本库做子串层传播检测。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .chunk import chunk_text
from .normalize import normalize


@dataclass
class TaintRecord:
    call_id: str
    tool: str
    ts_ms: int
    raw_text: str
    chunks: list[str]


class TaintStore:
    def __init__(self, path: Path | str | None = None):
        self._records: dict[str, TaintRecord] = {}
        self.path = Path(path) if path else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        call_id: str,
        tool: str,
        text: str,
        ts_ms: int | None = None,
    ) -> TaintRecord:
        rec = TaintRecord(
            call_id=call_id,
            tool=tool,
            ts_ms=ts_ms if ts_ms is not None else int(time.time() * 1000),
            raw_text=text,
            chunks=chunk_text(normalize(text)),
        )
        self._records[call_id] = rec
        if self.path is not None:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "call_id": rec.call_id,
                            "tool": rec.tool,
                            "ts_ms": rec.ts_ms,
                            "raw_text": rec.raw_text,
                            "chunks": rec.chunks,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return rec

    def get(self, call_id: str) -> TaintRecord | None:
        return self._records.get(call_id)

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self):
        return iter(self._records.values())
