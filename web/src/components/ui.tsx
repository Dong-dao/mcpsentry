import type { ReactNode } from "react";
import { VERDICT_LABEL, type VerdictType } from "../types";
import { href } from "../router";

const TONE: Record<VerdictType, string> = {
  exfiltration: "v-bad",
  forbidden_call: "v-bad",
  poisoning_executed: "v-bad",
  rug_pull_triggered: "v-warn",
  attack_failed: "v-good",
  n_a_negative_control: "v-info",
};

export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-base font-semibold text-slate-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function VerdictBadge({ type }: { type: VerdictType | null | undefined }) {
  if (!type) return <span className="badge v-info">未运行</span>;
  // 判定名与净效果分两行：运行台历史表的判定列只有 ~96px，
  // 挤在一枚胶囊里会被压成两字宽、中文逐字竖排。
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span className={`badge ${TONE[type] ?? "v-info"}`}>{VERDICT_LABEL[type] ?? type}</span>
      {type !== "n_a_negative_control" && (
        <span className={`mono ${type === "attack_failed" ? "text-good" : "text-bad"}`}>
          {type === "attack_failed" ? "防御生效" : "攻击成功"}
        </span>
      )}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "done" ? "v-good" : status === "error" ? "v-bad" : "v-warn";
  return <span className={`badge ${tone}`}>{status}</span>;
}

export function StatCard({
  label,
  value,
  hint,
  tone = "text-slate-100",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="panel">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "加载中…" }: { label?: string }) {
  return <div className="panel text-sm text-slate-400">{label}</div>;
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="panel border-rose-500/40 bg-rose-500/10 text-sm text-bad">
      <div className="font-semibold">接口调用失败</div>
      <div className="mono mt-2 break-all opacity-90">{message}</div>
      <div className="mt-2 text-xs text-slate-400">
        后端未启动？在仓库根目录执行{" "}
        <code className="mono rounded bg-ink px-1.5 py-0.5">python -m platform_api serve</code>，
        然后刷新本页。
      </div>
    </div>
  );
}

export function KeyValue({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-1">
          <dt className="text-xs text-slate-400">{k}</dt>
          <dd className="mono text-right text-slate-200">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function NavLink({
  path,
  active,
  children,
}: {
  path: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <a
      href={href(path)}
      className={`rounded-lg px-3 py-1.5 text-sm transition ${
        active ? "bg-sky-500/15 text-sky-100" : "text-slate-400 hover:bg-panel hover:text-slate-200"
      }`}
    >
      {children}
    </a>
  );
}
