"""JSONL 全流量日志。

D2 范围：会话级追加写，方向/方法/载荷全量记录；载荷含不可序列化对象时以 repr 兜底。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class FlowLogger:
    def __init__(self, path: Path | str | None):
        self.path = Path(path) if path else None
        self.session_id = uuid.uuid4().hex[:8]
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, direction: str, method: str, payload: Any) -> None:
        if self.path is None:
            return
        entry = {
            "session_id": self.session_id,
            "ts_ms": int(time.time() * 1000),
            "direction": direction,
            "method": method,
            "payload": payload,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
