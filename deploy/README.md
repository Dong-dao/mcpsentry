# deploy/ — ECS 后端 + Qoder Sites 前端

分工文档 §6 的第 4 项。**本机没有 Docker**，所以 `Dockerfile.api` / `Caddyfile` 属于
"结构已校验、未在本地构建跑通"的资产：compose YAML 用 PyYAML 解析过、容器 CMD
`python -m platform_api serve --host 0.0.0.0 --port 8000` 在宿主机直接跑过、Caddyfile
括号配平检查过，但真正的 `docker build` 与证书签发要在 ECS 上完成（见 §5 校验命令）。

## 1. 拓扑

```
评委/用户 ──HTTPS──> Qoder Sites（web/dist 静态文件）
                          │  fetch https://api.<域名>/api/*   ← MCPSENTRY_ORIGINS 放行这一个来源
                          ▼
                    Caddy(:80/:443, 自动证书)
                          │  reverse_proxy /api/* /docs /openapi.json
                          ▼
                    api 容器(:8000, 仅容器网)
                      ├─ /app/bench/results        ← 宿主机卷，120 组产物留在盘上
                      └─ /app/platform_api/data    ← 宿主机卷，SQLite 历史索引
```

两个卷是硬要求：重建容器不能丢证据。`bench/metrics/summary.json` 与
`platform_api/demo/*.json` 已经打进镜像，冷启动第一屏就有数字和 demo。

## 2. 首次上云（ECS 2C4G，Ubuntu 22.04）

```bash
# 0) 阿里云控制台：安全组放行 22/80/443；域名 A 记录指到公网 IP
sudo apt-get update && sudo apt-get install -y git docker.io docker-compose-plugin

git clone git@github.com:Dong-dao/mcpsentry.git && cd mcpsentry

# 1) 卷目录要先存在且属于容器里的 uid（Dockerfile 里固定 10001）
#    不存在时 Docker 会以 root 建目录，平台写产物直接 PermissionError
mkdir -p bench/results platform_api/data
sudo chown -R 10001:10001 bench/results platform_api/data

# 2) 配置
cp deploy/.env.example deploy/.env && $EDITOR deploy/.env   # MCPSENTRY_DOMAIN / MCPSENTRY_ORIGIN

# 3) 起服务（第一次会构建 api 镜像，前端产物要提前在本地 build 好）
cd web && npm ci && npm run build && cd ..
cd deploy && docker compose up -d --build
```

`MCPSENTRY_ORIGIN` 留空时平台**只接受同源请求**——也就是说只有走同一台 Caddy 直出
`web/dist` 的私有化部署才需要填它；把前端放 Qoder Sites（跨域）才必须填 Sites 的 origin。

## 3. 前端发布到 Qoder Sites

```bash
cd web
npm ci
VITE_API_BASE=https://api.<你的域名> npm run build   # 跨域部署才需要；同域反代留空
```

构建产物 `web/dist/` 是纯静态、相对 base（`base: "./"`），Sites 直接托管即可。
后端侧把 Sites 的 origin 写进 `MCPSENTRY_ORIGINS`（逗号分隔）后 `docker compose up -d` 重启，
否则浏览器会报 CORS——`/api/health` 能通但页面空白通常就是这个。

发布是对外动作：需要 B 明确确认后再执行（比赛要求"公网链接、评委点开即用"）。

## 4. 验证清单

在 ECS 上：

```bash
docker compose ps                                  # api healthy、caddy running
curl -I https://$MCPSENTRY_DOMAIN/api/health       # 200
curl -s https://$MCPSENTRY_DOMAIN/api/health | python3 -m json.tool | head
#   期望 demo_bundled/metrics_bundled/runs_present 全 true
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile   # 容器内
```

浏览器（无痕窗口，避免缓存）：

- [ ] `#/` 落地页有数字（91% → 9%、误报 0.0%、回放 16/16）与三档定价
- [ ] `#/demo` 两栏并排：左"数据外渗成功"+ 红色送达边，右"攻击失败"+ 绿色拦截边
- [ ] `#/dashboard` 点任意一行出污点图；导出 md/html/json 三个链接都能下载
- [ ] `#/metrics` 设计目标对照表无 NaN
- [ ] 控制台无 CORS/404；后端日志无 Traceback

## 5. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面空白，`/api/health` 单独能通 | `MCPSENTRY_ORIGINS` 没含 Sites origin | 填上并重启 api |
| 平台运行报 PermissionError | 卷目录属主是 root | `chown -R 10001:10001`（见 §2 第 1 步） |
| 跑矩阵时整台机器卡死 | 并发超过 2 核 | `MCPSENTRY_JOBS=1`；矩阵请用 `python -m bench matrix` 在 SSH 会话里跑，不要从 `/api/matrix` 点 |
| 点"运行单格"返回 401 | 启用了 Caddyfile 里注释掉的 basic_auth | 演示期解掉，或给评委只读预置 demo |
| 证书没签发 | 域名未解析 / 80 被安全组挡 | 先 `curl -v http://<域名>/.well-known/acme-challenge/` 探路 |
| 产物不见了 | 卷被 `docker compose down -v` 带走 | 别用 `-v`；卷是宿主机目录，`down` 不带 `-v` 才安全 |

## 6. 备份与回滚

```bash
# 证据备份：产物 + 历史索引，够小，直接 tar 到对象存储
tar czf mcpsentry-results-$(date +%F).tgz bench/results platform_api/data

# 回滚：镜像按 tag 留一份旧的
docker tag mcpsentry-api:latest mcpsentry-api:$(date +%F) && docker compose up -d --build
# 回退 = 改 compose 的 image: mcpsentry-api:<旧日期> 再 up -d
```

`bench/results` 是评分依据，丢了要重跑 66 组真实攻击才能复原；任何 `docker system prune`
之前先确认卷在宿主机上而不是命名卷里。

## 7. 安全边界

- 只监听 443（80 仅用于 ACME 跳转）；api 容器不发布到宿主机端口。
- 三个写接口（`/api/runs` `/api/demo` `/api/matrix`）都会消耗算力并真的投放攻击，
  靶标是自建靶场、sink 是 mock，不发真信、不出网；`/api/matrix` 另需 `confirm=true`。
- 密钥只走运行时 env（`DASHSCOPE_API_KEY`），不进镜像、不进 git；语义层没有 key 也能跑，
  只是退化为子串层。
- 报告与图全部来自产物文件，平台层不做任何判定，公网实例上不存在"能改判定"的入口。

## 8. 文件

| 文件 | 作用 |
|---|---|
| `Dockerfile.api` | 后端镜像（python:3.13-slim，非 root uid 10001，含健康检查） |
| `docker-compose.yml` | api + caddy，卷与来源开关都在这里 |
| `Caddyfile` | HTTPS、`/api` 反代、静态兜底、POST 请求体上限、可选 Basic Auth |
| `.env.example` | 需要填的四个变量（复制成 `.env`，`.env` 不进 git） |
