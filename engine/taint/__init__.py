"""污点追踪包。

D3：工具分类、归一化、分块、会话级污点存储与 tools/call 源标记。
D4：子串层传播检测 + sink 策略（alert/block + 能力降级）。
D5：描述投毒静态扫描、rug-pull 哈希钉扎、语义判定层。
"""

from .classify import ToolClass, classify_tool
from .desc_scan import DescScanResult, scan_description
from .detect import detect_taint
from .normalize import normalize
from .rugpull import RugPullEvent, RugPullPinner
from .semantic import K, SemanticJudge, SemanticVerdict
from .store import TaintStore

__all__ = [
    "ToolClass",
    "classify_tool",
    "DescScanResult",
    "scan_description",
    "detect_taint",
    "normalize",
    "RugPullEvent",
    "RugPullPinner",
    "K",
    "SemanticJudge",
    "SemanticVerdict",
    "TaintStore",
]
