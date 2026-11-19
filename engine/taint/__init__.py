"""污点追踪包：工具分类、归一化、分块、会话级污点存储（D3）与子串层传播检测（D4）。

D3：tools/call 拦截 + SOURCE 源标记。D4：污点传播 + sink 策略（alert/block + 能力降级）。
D5 在此之上做语义层判定；描述扫描与 rug-pull 挂 tools/list。
"""

from .classify import ToolClass, classify_tool
from .detect import detect_taint
from .normalize import normalize
from .store import TaintStore

__all__ = ["ToolClass", "classify_tool", "detect_taint", "normalize", "TaintStore"]
