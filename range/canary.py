"""金丝雀派生：与判定 oracle 设计 §2 一致——8 位十六进制、由 run seed 决定。

采用 sha256(str(seed)) 前 8 位（A 在 tests/test_e2e_attack.py 的同一约定），
保证 B 的 runner、A 的测试和任何手工复核都能从 seed 重算出同一令牌。
"""

from __future__ import annotations

import hashlib

PREFIX = "CANARY-"


def canary_for_seed(seed: int) -> str:
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return PREFIX + digest[:8]


def is_canary(token: str) -> bool:
    return token.startswith(PREFIX) and len(token) == len(PREFIX) + 8
