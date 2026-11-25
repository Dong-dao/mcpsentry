import { Suspense, lazy } from "react";
import { exportUrl } from "../api";
import type { RunDetail, TrajectoryStep } from "../types";
import { ATTACK_LABEL } from "../types";
import { KeyValue, Loading, Panel, VerdictBadge } from "./ui";

const TaintGraphView = lazy(() => import("./TaintGraph"));

const attackClass = (d: RunDetail) => d.config?.attack?.class_ ?? d.config?.attack?.class ?? "—";

function Clip({ text, lines = 4 }: { text: string; lines?: number }) {
  return (
    <pre
      className="mono whitespace-pre-wrap break-all text-slate-300"
      style={{ maxHeight: `${lines * 1.35}em`, overflow: "hidden" }}
      title={text}
    >
      {text}
    </pre>
  );
}

function TrajectoryCard({ step }: { step: TrajectoryStep }) {
  return (
    <li className="rounded-lg border border-line bg-ink/60 p-4">
      <div className="mono text-slate-400">第 {step.round} 轮</div>
      <div className="mt-2 text-sm font-semibold text-slate-400">载荷</div>
      <Clip text={step.payload} />
      <div className="mt-2 text-sm font-semibold text-slate-400">靶标回复</div>
      <Clip text={step.target_response} lines={3} />
      <div className="mt-2 text-sm font-semibold text-slate-400">工具调用</div>
      <div className="mono text-slate-300">
        {step.tool_calls?.length ? step.tool_calls.map((c) => c.tool).join("、") : "—"}
      </div>
    </li>
  );
}

/** 单组运行详情：判定 → 证据 → 污点图 → 轨迹 → sink 载荷 → 修复建议。 */
export default function RunDetailPanel({ detail }: { detail: RunDetail }) {
  const { verdict, meta, config } = detail;
  const defense = config?.defense?.proxy ? `on（${config.defense.policy}）` : "off";

  return (
    <div className="space-y-4">
      <Panel
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span className="mono">{detail.run_id}</span>
            <VerdictBadge type={verdict?.type} />
          </span>
        }
        subtitle={`${ATTACK_LABEL[attackClass(detail)] ?? attackClass(detail)} · 防御 ${defense} · seed ${
          config?.attack?.seed
        }`}
        right={
          <div className="flex flex-wrap gap-2">
            {(["md", "html", "json"] as const).map((f) => (
              <a key={f} className="btn" href={exportUrl(detail.run_id, f)} download>
                导出 {f}
              </a>
            ))}
          </div>
        }
      >
        <KeyValue
          rows={[
            ["靶标", `${config?.target?.id} ${config?.target?.name ?? ""}`],
            ["判定证据", verdict?.evidence || "—"],
            ["轮次", `${meta?.rounds_used ?? "—"} / ${config?.attack?.max_rounds ?? "—"}`],
            ["金丝雀", <span className="text-bad">金丝雀令牌 · {config?.oracle?.canary ?? "—"}</span>],
            ["禁用 sink", (config?.oracle?.forbidden_sinks ?? []).join("、") || "—"],
            ["子串/语义命中", `${detail.report?.metrics?.substring_hits ?? 0} / ${detail.report?.metrics?.semantic_layer_calls ?? 0}`],
            ["能力降级", detail.report?.metrics?.downgraded ? "已降级（不可信内容）" : "未触发"],
            ["replay_hash", <span title={meta?.replay_hash}>{(meta?.replay_hash ?? "—").slice(0, 16)}…</span>],
            ["engine", config?.engine_version ?? "—"],
            ["产物目录", <span title={detail.path}>{detail.subdir}/{detail.run_id}</span>],
          ]}
        />
      </Panel>

      <Panel
        title="污点传播图"
        subtitle="绿色边 = 代理在进 sink 前拦下；红色边 = 载荷真的送达后端（防御关闭时的一手证据）"
      >
        <Suspense fallback={<Loading label="加载污点传播图…" />}>
          <TaintGraphView graph={detail.graph} />
        </Suspense>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          图例：绿边 = 代理拦下，红线 = 载荷送达；放大后可拖动查看每一轮的工具调用。
        </p>
      </Panel>

      <Panel title={`攻击轨迹（${detail.report?.trajectory?.length ?? 0} 轮）`}>
        {detail.report?.trajectory?.length ? (
          <>
            <ul className="space-y-3 md:hidden">
              {detail.report.trajectory.map((s) => (
                <TrajectoryCard key={s.round} step={s} />
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full table-fixed">
                <thead>
                  <tr>
                    <th className="th w-12">轮</th>
                    <th className="th">载荷</th>
                    <th className="th">靶标回复</th>
                    <th className="th w-40">工具调用</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.report.trajectory.map((s) => (
                    <tr key={s.round}>
                      <td className="mono td text-slate-400">{s.round}</td>
                      <td className="td">
                        <Clip text={s.payload} />
                      </td>
                      <td className="td">
                        <Clip text={s.target_response} lines={3} />
                      </td>
                      <td className="mono td text-slate-300">
                        {s.tool_calls?.length ? s.tool_calls.map((c) => c.tool).join("、") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-400">该格未执行攻击（负对照），无轨迹。</p>
        )}
      </Panel>

      {detail.sink_capture?.length > 0 && (
        <Panel
          title={`sink 捕获（${detail.sink_capture.length} 条，mock 后端原样落盘）`}
          subtitle="靶场不发真信、不出网：这里就是「外渗到底出去了什么」的唯一真相"
        >
          <div className="space-y-3">
            {detail.sink_capture.map((c, i) => (
              <div key={`${c.tool}-${i}`} className="rounded-lg border border-bad/30 bg-rose-500/5 p-4">
                <div className="mono text-bad">
                  {c.tool} · {new Date(c.ts).toLocaleTimeString()}
                </div>
                <pre className="mono mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all text-slate-300">
                  {JSON.stringify(c.payload, null, 1)}
                </pre>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="修复建议">
        <ul className="space-y-2 text-sm text-slate-300">
          {(detail.remediation ?? []).map((line, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-sky-400">·</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
