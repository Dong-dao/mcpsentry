"""污点分块（规格 §3）：按句子/换行切分，块长 ≤240 字符，相邻块 40 字符重叠。

输入是已归一化的文本（§4，空白已折叠为单空格、换行变空格）。切分只在句末标点后
进行、不增删任何字符，因此每块都是归一化原文的连续片段——复制内容经同一归一化后
必然是某块的子串，跨块边界的复制由 40 字符重叠捕获。单段超过 240 字符时按
240/40 窗口切。长度低于 MIN_MATCH 的尾块丢弃（§5 最小匹配阈值，低于它不可能命中）。
"""

from __future__ import annotations

import re

MAX_CHUNK = 240
OVERLAP = 40
MIN_MATCH = 12

_SENTENCE_END = "。！？!?.;；"
_SEGMENT_RE = re.compile(rf"(?<=[{_SENTENCE_END}])|\n+")


def split_segments(normalized: str) -> list[str]:
    return [seg for seg in _SEGMENT_RE.split(normalized) if seg]


def _window_chunks(segment: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(segment):
        window = segment[start : start + MAX_CHUNK]
        if len(window) >= MIN_MATCH:
            chunks.append(window)
        if start + MAX_CHUNK >= len(segment):
            break
        start += MAX_CHUNK - OVERLAP
    return chunks


def chunk_text(normalized: str) -> list[str]:
    chunks: list[str] = []
    for seg in split_segments(normalized):
        if len(seg) > MAX_CHUNK:
            chunks.extend(_window_chunks(seg))
            continue
        if not chunks:
            chunks.append(seg)
            continue
        if len(chunks[-1]) + len(seg) <= MAX_CHUNK:
            chunks[-1] += seg
            continue
        # 新块以重叠前缀开头；前缀截到能装下本段为止
        prefix = chunks[-1][-OVERLAP:]
        room = MAX_CHUNK - len(seg)
        if room <= 0:
            prefix = ""
        elif room < len(prefix):
            prefix = prefix[-room:]
        chunks.append(prefix + seg)
    return [c for c in chunks if len(c) >= MIN_MATCH]
