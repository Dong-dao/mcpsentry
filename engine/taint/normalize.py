"""污点归一化（规格 §4）：确定性层输入变换，按顺序执行。"""

from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff\u2060-\u2064]")
WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = ZERO_WIDTH_RE.sub("", t)
    t = t.casefold()
    t = WHITESPACE_RE.sub(" ", t).strip()
    return t
