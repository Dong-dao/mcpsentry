"""MCPSentry 靶场（成员 B 交付）：T1–T5 靶标 Agent 与恶意 MCP 工具面。

对外只暴露三样东西：
- specs：靶标注册表（工具面、载体、分类覆盖、端口）
- backend：stdio MCP 后端（真靶标工具 + mock sink 落盘）
- victim/agent_app：确定性受害者策略，HTTP 形态见 range.agent_app

命名说明：包名 range 遮蔽内置 range()，外部请使用
`import range.specs as specs` / `from range.specs import ...` 形式导入。
"""

ENGINE_CONTRACT_VERSION = "1.0"
