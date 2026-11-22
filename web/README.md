# web/ — 前端（B）

React 18 + Vite 5 + TypeScript + TailwindCSS，污点图用 `@xyflow/react`，图表用 `Recharts`。
构建产物是纯静态文件，Qoder Sites 直接托管；数据全部走 `/api/*`，前端不做任何判定。

## 跑起来

```bash
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5173     # http://127.0.0.1:5173
```

dev 服务器把 `/api` 反代到 `http://127.0.0.1:8000`（另开一个终端）：

```bash
python -m platform_api serve --port 8000
```

要连别处的后端：`VITE_PROXY_TARGET=http://1.2.3.4:8000 npm run dev`。
生产构建：`npm run build` → `web/dist/`；跨域部署时设 `VITE_API_BASE`，同域反代留空即可。

## 页面

| 路由 | 内容 | 数据来源 |
|---|---|---|
| `#/` | 落地页：机制说明、靶标矩阵、实测数字、**定价**（免费扫描 / 深度报告 ¥2000–10000 / 私有化） | `/api/metrics` + `/api/targets` |
| `#/demo` | 一键 demo：同一格 off/block 并排，判定 → 载荷 → 拦截证据，可展开完整报告 | `/api/demo/preset`（**不消耗算力**） |
| `#/dashboard` | 运行台：历史列表 + 过滤 + 单格运行 + 批量矩阵（需显式勾选）+ 单组详情 | `/api/runs`、`POST /api/runs`、`POST /api/matrix` |
| `#/metrics` | 指标：ASR、有效性、延迟开销、误报分拆、设计目标对照、格级明细 | `/api/metrics?refresh=` |

路由是 hash 路由（`src/router.ts`）：静态托管不需要服务端 rewrite。

## 数据契约

`src/types.ts` 与 `engine/contracts.py`（`SCHEMA_VERSION 1.0`）以及 `platform_api` 的视图模型一一对应。
两处容易踩的点已经写进类型：

- `config.attack.class_`：pydantic 按字段名序列化，别名 `class` 只在入参侧；
- `meta.defense` 只有 `off`/`on` 两态，矩阵的 `on` 就是 block 策略——UI 上标成 block，过滤参数仍传 `on`。

## 污点图语义

节点分列由后端 `graph.column` 给出（攻击者 → Agent → 工具调用 → sink），边的 `state` 决定颜色：

| state | 含义 | 颜色 |
|---|---|---|
| `payload` | 注入内容进入 Agent 上下文 | 红虚线 |
| `call` | 常规工具调用（`hits` = 逐轮重复次数） | 灰 |
| `blocked` | 污点命中并被拦下 | 绿 |
| `tainted` | 污点命中但放行（alert 档） | 黄虚线 |
| `captured` | 载荷真的送达后端 | 红实线（动画） |

绿色 = 防御生效，红色 = 数据出去了。这个区分不能糊：防御关闭时代理不在链路上，
根本没有 `blocked` 边，只能靠 `captured`（靶场后端落盘的 sink 载荷）说明"外渗确实发生了"。

## 已知边界

- 前端不缓存判定结果，切换防御档必须重新请求；一键 demo 是唯一可以离线（无算力）看的页面。
- 大图（>60 节点）没有做聚合，只做了边去重；后续可考虑按工具折叠。
- 没有登录与多租户：这是评测平台 MVP，公网部署由 Caddy 限制来源，见 `deploy/`。
