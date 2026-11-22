"""证据流读取：实现 engine.attacks.engine.EvidenceSource 协议。

判定只读落盘文件（sink_capture.jsonl + flow.jsonl），与 A 的 oracle 设计 §1 一致：
任何人拿同一批文件都能手工复核 verdict。运行前清空，避免跨 run 证据串味。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.attacks.engine import EvidenceSource

from . import workspace as ws


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


class FileEvidence(EvidenceSource):
    def __init__(self, workdir: Path):
        self.ws = ws.Workspace(Path(workdir))

    def snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return read_jsonl(self.ws.capture), read_jsonl(self.ws.flow)

    def reset(self) -> None:
        """清掉上一组运行的证据（同 workdir 复用时必须调用）。"""
        for path in (self.ws.capture, self.ws.flow, self.ws.taint_log):
            path.unlink(missing_ok=True)
