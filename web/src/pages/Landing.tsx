import { useEffect, useState } from "react";
import { api } from "../api";
import { AsrByTargetChart, EffectivenessChart } from "../components/MetricsCharts";
import { ErrorNote, Loading, Panel, StatCard, pct } from "../components/ui";
import { href } from "../router";
import type { Health, MetricsPayload, TargetsResponse } from "../types";
import { ATTACK_LABEL } from "../types";

const STEPS = [
  ["接入", "把 MCP 配置交给平台：后端 server、工具清单、可信度标注。靶场里 5 个靶标已经就绪。"],
  ["投放", "自适应攻击引擎按 4 类攻击 × 3 个变体逐轮改写载荷，命中即停——不是静态扫描通过率。"],
  ["拦截", "污点代理在工具边界给返回值打标记，进 sink 前查污点：命中就拒调用，并留下污点边作为证据。"],
  ["出报告", "攻击轨迹、污点传播图、判定证据、修复建议一次给全，附 replay_hash 可原样复跑。"],
] as const;

const INNOVATIONS = [
  ["防御层位", "把信息流控制落到 MCP 工具边界：确定性保证，与模型层防御正交，可以叠加。"],
  ["攻击驱动验证", "攻击引擎是防御的验收器。ASR 是打出来的，不是估出来的。"],
  ["确定性 oracle", "金丝雀令牌让「外渗」这件事零争议，绕开 LLM 当裁判的可信度问题。"],
  ["供应链视角", "工具描述哈希钉扎，覆盖 rug-pull（装完之后偷偷改描述）这一新攻击面。"],
] as const;

const TIERS = [
  {
    name: "免费基础扫描",
    price: "¥0",
    unit: "",
    items: ["单靶标 × 单攻击类 1 组运行", "污点传播图与判定证据", "平台在线可玩，无需部署"],
    cta: "打开一键 demo",
    href: href("/demo"),
    accent: false,
  },
  {
    name: "付费深度报告",
    price: "¥2,000–10,000",
    unit: "/ 份",
    items: [
      "120 组矩阵：5 靶标 × 4 攻击类 × 3 种子 × off/block",
      "自适应攻击全变体与首轮/自适应 ASR 拆分",
      "误报分拆（设计性压力任务 vs 常规任务）",
      "修复建议 + 可复现 replay_hash + json/md/html 导出包",
    ],
    cta: "看一份真实报告",
    href: href("/dashboard"),
    accent: true,
  },
  {
    name: "私有化部署",
    price: "面议",
    unit: "",
    items: ["自有 MCP 配置接入", "内网 Docker Compose + Caddy", "回归评测常态化（新版本自动重跑矩阵）"],
    cta: "在仓库提 Issue",
    href: "https://github.com/Dong-dao/mcpsentry/issues",
    accent: false,
  },
] as const;

export default function Landing() {
  const [data, setData] = useState<{ metrics: MetricsPayload; targets: TargetsResponse; health: Health } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.metrics(), api.targets(), api.health()])
      .then(([metrics, targets, health]) => setData({ metrics, targets, health }))
      .catch((e: Error) => setError(e.message));
  }, []);

  const m = data?.metrics;
  const off = m ? Object.values(m.asr_by_target.off) : [];
  const on = m ? Object.values(m.asr_by_target.block) : [];
  const asrOff = off.length ? off.reduce((a, b) => a + b.asr * b.runs, 0) / off.reduce((a, b) => a + b.runs, 0) : null;
  const asrOn = on.length ? on.reduce((a, b) => a + b.asr * b.runs, 0) / on.reduce((a, b) => a + b.runs, 0) : null;

  return (
    <div className="space-y-10">
      <header className="pt-6">
        <div className="badge v-info">AI 安全 · MCP 工具链</div>
        <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-snug text-slate-50 sm:text-4xl">
          给你的 Agent 做一次<span className="text-sky-300">能复现</span>的红队评测
        </h1>
        <p className="mt-4 max-w-2xl text-slate-400">
          MCPSentry 在 MCP 工具边界做污点跟踪：外部内容打上标记，进 sink 之前查一次。
          攻击引擎负责把它骗过去，判定用金丝雀令牌——不靠模型自己当裁判。
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <a className="btn btn-primary" href={href("/demo")}>
            一键 demo（不消耗算力）
          </a>
          <a className="btn" href={href("/dashboard")}>
            打开运行台
          </a>
          <a className="btn" href={href("/metrics")}>
            看基准数字
          </a>
        </div>
      </header>

      {error && !m && (
        <ErrorNote
          message={`${error}\n落地页的数字来自后端 /api/metrics；后端没起时这里会空着，其余页面同样需要后端。`}
        />
      )}

      {m && (
        <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="外渗 ASR（无防御）"
            value={asrOff === null ? "—" : pct(asrOff)}
            hint={`${m.counts.executed} 组执行 / ${m.counts.negative_control} 组负对照（全格加权）`}
            tone="text-bad"
          />
          <StatCard
            label="ASR（代理 block）"
            value={asrOn === null ? "—" : pct(asrOn)}
            hint="同一批格只多了一个代理；残留全部来自 T3 描述投毒——那一档只能降级能力，不能拒调用"
            tone="text-good"
          />
          <StatCard
            label="正常任务误报"
            value={pct(m.normal_suite.fpr_excluding_design, 1)}
            hint={`${m.normal_suite.unintended_blocked}/${m.normal_suite.total - m.normal_suite.intended_pressure} 条常规任务被误拦`}
            tone="text-good"
          />
          <StatCard
            label="回放一致率"
            value={`${m.canonical.replay_consistency[0]}/${m.canonical.replay_consistency[1]}`}
            hint={`Δp95 ${m.latency_overhead.p95_delta_ms ?? "—"} ms · engine ${m.engine_version}`}
            tone="text-info"
          />
        </section>
      )}

      <Panel title="怎么工作" subtitle="四步闭环，每步都留一手证据">
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="rounded-lg border border-line bg-ink/60 p-4">
              <div className="mono text-xs text-sky-300">0{i + 1}</div>
              <div className="mt-1 font-semibold text-slate-100">{title}</div>
              <p className="mt-2 text-sm leading-6 text-slate-400">{body}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="创新点" subtitle="机制设计，不是提示词加固">
          <ul className="space-y-3">
            {INNOVATIONS.map(([k, v]) => (
              <li key={k} className="text-sm leading-6">
                <span className="font-semibold text-slate-100">{k}</span>
                <span className="text-slate-400"> — {v}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="靶标" subtitle={data ? `${data.targets.matrix.applicable} 组适用格 / ${data.targets.matrix.negative_control} 组负对照` : "加载中"}>
          {data ? (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">靶标</th>
                  <th className="th">脆弱点</th>
                  <th className="th">适用攻击类</th>
                </tr>
              </thead>
              <tbody>
                {data.targets.targets.map((t) => (
                  <tr key={t.id}>
                    <td className="td">
                      <div className="font-medium text-slate-100">
                        {t.id} {t.name}
                      </div>
                      <div className="mono text-xs text-slate-500">{t.mcp_servers.join("、")}</div>
                    </td>
                    <td className="td text-xs text-slate-400">{t.vulnerability}</td>
                    <td className="td mono text-xs text-slate-300">
                      {t.applicable.map((c) => c.split("_")[0]).join(" / ")}
                      {t.na.length ? <span className="text-slate-600"> · N/A {t.na.map((c) => c.split("_")[0]).join("/")}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Loading label="读取靶标注册表…" />
          )}
        </Panel>
      </div>

      {m && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="ASR：防御 off vs block" subtitle="靶标聚合，基准规格 §2 的比对口径">
            <AsrByTargetChart metrics={m} />
          </Panel>
          <Panel title="防御有效性" subtitle="ASR_off − ASR_block，只统计适用格（§4 口径）">
            <EffectivenessChart metrics={m} />
            <ul className="mono mt-3 space-y-1 text-xs text-slate-400">
              {Object.entries(m.effectiveness_applicable_only).map(([cls, row]) => (
                <li key={cls}>
                  {ATTACK_LABEL[cls] ?? cls}：{pct(row.off.asr)} → {pct(row.on.asr)}
                  <span className="text-good"> （−{pct(row.delta)}）</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}

      <Panel title="定价" subtitle="评估报告即交付物，平台即接单流水线">
        <div className="grid gap-4 md:grid-cols-3">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`flex flex-col rounded-xl border p-5 ${
                t.accent ? "border-sky-500/60 bg-sky-500/5" : "border-line bg-ink/60"
              }`}
            >
              <div className="text-sm font-semibold text-slate-100">{t.name}</div>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="text-2xl font-semibold text-slate-50">{t.price}</span>
                <span className="text-xs text-slate-400">{t.unit}</span>
              </div>
              <ul className="mt-4 flex-1 space-y-2 text-sm text-slate-400">
                {t.items.map((i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-sky-400">·</span>
                    <span>{i}</span>
                  </li>
                ))}
              </ul>
              <a className="btn mt-5 justify-center" href={t.href}>
                {t.cta}
              </a>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
