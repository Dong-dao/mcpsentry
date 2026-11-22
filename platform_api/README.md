# platform_api/ — 后端平台（B）

把 `bench/results/**` 的原始产物读成前端能画的视图模型，并把"发起一组运行"这件事
变成一个受控的 HTTP 接口。判定、指标、复算一律在 `engine/` 与 `bench/` 侧，这里
**不复制第二套安全逻辑**——平台上看到的每个数字都能回溯到某个 `report.json`。

> 目录名是 `platform_api` 而不是分工文档 §8 写的 `platform`：顶层包名会遮蔽标准库
> `platform`，pydantic v2 在导入时调用 `platform.python_version()` 会直接崩。
> 这是 §8 命名的唯一偏离，功能划分不变。

## 目录

| 文件 | 职责 |
|---|---|
| `app.py` | FastAPI 路由：6 个读接口 + 3 个写接口 |
| `orchestr.py` | 运行编排：`RunRequest` 校验 → `bench.runner.run_cell`，带并发闸 |
| `reports.py` | 报告服务：读一组产物 + 把污点边摊成有向图（`taint_graph`） |
| `history.py` | 运行历史：SQLite 索引（`data/history.db`，gitignore） |
| `export.py` | 报告导出：json / markdown / 自包含 HTML（全量转义） |
| `demo.py` + `demo/t1-a2-pair.json` | 一键 demo 的预置包：真跑出来的成对证据，随代码提交 |

## 启动

```bash
pip install -r requirements.txt              # mcp<2 + fastapi/uvicorn/httpx + pytest
python -m platform_api serve --port 8000      # 打开 http://127.0.0.1:8000/docs
python -m platform_api build-demo             # 重新生成预置 demo 包（要真实算力）
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 存活 + 产物/指标/demo 包是否就绪 + 历史统计 |
| GET | `/api/targets` | 靶标注册表、攻击类、种子、矩阵规模（含 N/A 拆分） |
| GET | `/api/metrics?refresh=true` | `bench/metrics/summary.json`；`refresh` 时从 `results/` 复算 |
| GET | `/api/runs?limit&offset&target&attack_class&defense` | 历史列表（SQLite，分页/过滤） |
| GET | `/api/runs/{id}` | 单组详情：config / report / 轨迹 / flow / sink 捕获 / 污点图 |
| GET | `/api/runs/{id}/export?format=json\|md\|html` | 导出；HTML 自包含且转义攻击者文本 |
| POST | `/api/runs` | 发起一组运行，立刻回 `run_id`（202，后台执行） |
| POST | `/api/demo` | 同一格 off/block 成对运行 |
| GET | `/api/demo/preset` | 预置 demo 包，前端零算力可读 |
| POST | `/api/matrix` | 批量跑格，**必须 `confirm=true`**（矩阵是证据底座，防误点覆盖产物） |

`/api/runs/{id}` 的 `graph` 结构（前端 `@xyflow/react` 直接吃）：

```json
{"nodes": [{"id": "t-000000000000", "label": "read_doc · {...}", "kind": "call|sink|agent|attacker",
            "column": 2}],
 "edges": [{"id": "t-...->t-...", "source": "...", "target": "...",
            "label": "substring/blocked", "state": "blocked|tainted|call|captured|payload",
            "hits": 6, "snippet": "...", "sink_field": "args.body"}]}
```

- `state`：`blocked`=代理拦下（防御生效）｜`tainted`=放行但带标记（alert）｜`call`=普通调用｜
  `captured`=后端落盘的 sink 载荷（防御关闭时唯一可得的事实）｜`payload`=注入进入 Agent。
- `hits`：自适应攻击逐轮重复同一批调用，边按 (source,target) 去重后累计次数。
- 防御关闭时代理不在链路上，`taint_edges` 为空 → 图用 `sink_capture.jsonl` 补出送达节点，
  所以"攻击成功"那一栏不会是空白画布，但它不含任何检出语义。

## 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `MCPSENTRY_DB` | `platform_api/data/history.db` | 历史索引位置 |
| `MCPSENTRY_JOBS` | `2` | 并发运行闸（ECS 2C4G，超过就会互相抢 CPU 污染延迟） |
| `MCPSENTRY_ORIGINS` | 空（=只允许同源） | 逗号分隔的前端 origin，才启用 CORS |
| `DASHSCOPE_API_KEY` | 未设置 | 语义层；不设也能跑，代理自动只走子串层 |

## 安全边界

- 三个写接口都是**算力开关**：默认无 CORS、无鉴权，只用于本机/内网演示。公网部署必须放在
  Caddy 之后（见 `deploy/`），由 Caddy 做来源与速率限制；`/api/matrix` 另需显式 `confirm`。
- HTML 导出把每段文本 `html.escape`：载荷是攻击者可控内容，未转义等于在报告里做存储型 XSS。
- 平台不产生真实网络副作用：sink 全部是靶场 mock，`send_email` 只追加一行 JSONL。
- 单测：`tests/test_platform_api.py`（12 项，含"平台运行不得覆盖矩阵正式产物"、
  HTML 转义、`confirm` 缺失必须 400、历史导入幂等）。
