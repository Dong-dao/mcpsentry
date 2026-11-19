"""描述投毒静态扫描（规格 §8）：tools/list 时对每条工具描述跑 R1–R5 规则。

每条描述产出 poison_score（命中规则数），≥2 记为高危。R1 直接检测零宽字符而非
"归一化前后长度差"——空白折叠会让任何连续空格误报，零宽字符才是 §8 R1 的攻击面。
R2 要求敏感词经同形字替换后出现、而原文不出现（即"伪装"才计数，明文出现不属 R2）。
R3 的 send 模式收窄为"send <数据/内容/代词> to"：规格原文 send.*to 会把
"Send an email to a recipient" 这类标准工具描述误报（FPR 预算不能花在这）。
R5 的"与工具名语义无关度"子规则需要 LLM 评分，暂缓（§8 标注成本低可全量，D6+ 评估）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import ZERO_WIDTH_RE

R3_IMPERATIVE_RE = re.compile(
    r"ignore\s+previous|instead|disregard|发送.{0,20}到|"
    r"send\s+(it|this|that|them|him|her|these|those|data|content|files?|documents?|logs?|everything|all)\s+to|"
    r"base64|\bexec\b|exfiltrate",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EXFIL_VERB_RE = re.compile(
    r"发送|转发|上传|传出|send|forward|upload|post|exfiltrate|deliver",
    re.IGNORECASE,
)

# 常见混淆对（西里尔/希腊字母冒充拉丁字母）；只做小写后替换
HOMOGLYPHS = str.maketrans(
    {"о": "o", "а": "a", "е": "e", "с": "c", "і": "i", "р": "p", "х": "x", "ѕ": "s", "ԁ": "d", "у": "y"}
)
SENSITIVE_WORDS = (
    "password", "passwd", "token", "credential", "secret", "admin",
    "密码", "令牌", "凭据", "管理员",
)

MAX_DESC_LEN = 2000


@dataclass
class DescScanResult:
    tool: str
    score: int = 0
    rules: list[str] = field(default_factory=list)

    @property
    def high_risk(self) -> bool:
        return self.score >= 2


def scan_description(tool: str, description: str) -> DescScanResult:
    result = DescScanResult(tool=tool)

    if ZERO_WIDTH_RE.search(description):
        result.score += 1
        result.rules.append("R1_zero_width")

    lowered = description.casefold()
    translated = lowered.translate(HOMOGLYPHS)
    for word in SENSITIVE_WORDS:
        if word in translated and word not in lowered:
            result.score += 1
            result.rules.append(f"R2_homoglyph:{word}")
            break

    if R3_IMPERATIVE_RE.search(description):
        result.score += 1
        result.rules.append("R3_hidden_imperative")

    if (URL_RE.search(description) or EMAIL_RE.search(description)) and EXFIL_VERB_RE.search(
        description
    ):
        result.score += 1
        result.rules.append("R4_url_email_plus_exfil_verb")

    if len(description) > MAX_DESC_LEN:
        result.score += 1
        result.rules.append("R5_length_over_2000")

    return result
