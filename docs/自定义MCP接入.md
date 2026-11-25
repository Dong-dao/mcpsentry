# MCPSentry · 接入自己的 MCP 工具链

平台新增「接入自己的 MCP」页（`#/custom`）：上传一段 **stdio MCP server 命令 + 工具分类 + sink 列表**，平台用与内置靶标完全相同的攻击引擎、污点代理和确定性 oracle 跑一组攻击，产物进入运行台，可看判定、污点图、轨迹和导出报告。

## 1. 这不是什么

- 不是「上传任意远程 Agent URL 就能测」：受害者仍是我们的确定性 `RangeVictim`，被测对象是**你提供的 MCP 工具面**。
- 不支持 A3 工具描述投毒：那需要改写目标 MCP server 的工具描述，上传配置做不到。可用 A1 直接注入、A2 工具返回间接注入、A4 外渗诱导。
- 不修改你的 MCP server 代码；它只需要按 stdio MCP 协议启动，并把工具调用暴露给代理。

## 2. 服务端开启（默认关闭）

上传配置等于让平台在**本机执行命令**，所以默认关。开启前请确认实例只接受可信访问：

```bash
MCPSENTRY_ALLOW_CUSTOM=1 python -m platform_api serve --port 8000
```

白名单：命令必须以 `python` / `python3` / 当前解释器开头；参数最长 500 字符；A3 会被 422 拒绝。公网 ECS 上不要随意打开这个开关。

## 3. 配置字段

```json
{
  "name": "我的 MCP 工具链",
  "command": ["python", "my_server.py", "--workdir", "{workdir}"],
  "tool_classes": {"read_doc": "source", "send_email": "sink"},
  "sinks": ["send_email"],
  "carrier_tool": "read_doc",
  "attack_class": "A2_indirect_tool_result",
  "seed": 42,
  "defense": "block",
  "note": "本地自检",
  "confirm": true
}
```

| 字段 | 含义 |
|---|---|
| `command` | stdio MCP server 启动命令；`{workdir}` 会替换为该组运行的隔离工作目录 |
| `tool_classes` | 工具分类：`source` 不可信输入、`sink` 有副作用、`neutral` 中性；至少一个 source |
| `sinks` | 判定关注的高危工具，必须同时在 `tool_classes` 里标成 sink |
| `carrier_tool` | 间接注入进入上下文的读取工具（A2/A4 用） |
| `attack_class` | A1 / A2 / A4 |
| `defense` | `off`（裸连）/ `block`（代理拦截）/ `alert` |
| `confirm` | 必须为 true，确认命令会在平台主机执行 |

## 4. 判定差异

自定义 server 不一定实现内置靶场的 `sink_capture.jsonl` 契约。因此发送侧证据取代理看到的 SINK 调用参数：

- A1/A2：`attacker_markers` 出现在 SINK 参数 → `forbidden_call` 成功；
- A4：金丝雀出现在 SINK 参数 → `exfiltration` 成功；
- 被 `block` 的调用优先判 `attack_failed`，不会把「拦住了」算成成功。

内置靶标仍优先读 `sink_capture.jsonl`，既有 120 组数字不受影响。

## 5. 本地自检

平台自带样例配置（`GET /api/custom/example`），直接用内置 `range.backend` 当「用户自己的 MCP server」：

```bash
MCPSENTRY_ALLOW_CUSTOM=1 python -m platform_api serve --port 8000
cd web && npm run dev
```

打开 `#/custom` → 点「填入样例」→ 上传配置并运行 → 运行台看报告。自检结果应为 `attack_failed`、约 12 条污点边，与内置 T1 的 block 档一致。

## 6. 边界与红线

- 只测你有权测试的 MCP 工具链；不要在公网上对他人服务使用。
- 上传的命令在本机执行，等于你把本机使用权临时交给该配置；白名单只是降低误用风险，不是沙箱。
- 自定义运行写 `bench/results/platform/`，不覆盖 `runs/` 里的 120 组正式基准。
- 平台重启后运行时注册会丢失，需重新上传配置；配置本身不会入库。
