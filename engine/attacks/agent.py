"""靶标 Agent 交互契约（D8 与 B 对齐的最小 HTTP 契约 + 本地可注入接口）。

最小 HTTP 契约（B 的靶场按此实现）：
    POST {agent_endpoint}
    {"payload": "<本轮注入内容>", "run_id": "..."}
    → 200 {"response": "<目标 Agent 的文本响应>"}
工具调用不在此响应里：由证据流（代理 flow log / mock sink 捕获）提供，
保证轨迹与判定全部可落盘复核。

本地测试用确定性受害者直接注入 TargetAgent 接口（见 tests/test_e2e_attack.py）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class AgentResponse:
    text: str
    raw: dict[str, Any] | None = None


@runtime_checkable
class TargetAgent(Protocol):
    async def act(self, user_message: str) -> AgentResponse: ...


class HTTPTargetAgent:
    def __init__(self, endpoint: str, run_id: str, timeout: float = 120.0):
        self.endpoint = endpoint.rstrip("/")
        self.run_id = run_id
        self.timeout = timeout

    async def act(self, user_message: str) -> AgentResponse:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.endpoint,
                json={"payload": user_message, "run_id": self.run_id},
            )
            resp.raise_for_status()
            data = resp.json()
        return AgentResponse(text=str(data.get("response", "")), raw=data)
