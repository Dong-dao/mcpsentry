"""污点追踪包：工具分类、归一化、分块与会话级污点存储（D3）。

D3 范围：tools/call 拦截 + SOURCE 源标记。D4 在此之上做子串层传播检测与 sink 策略。
"""

from .classify import ToolClass, classify_tool
from .normalize import normalize
from .store import TaintStore

__all__ = ["ToolClass", "classify_tool", "normalize", "TaintStore"]
