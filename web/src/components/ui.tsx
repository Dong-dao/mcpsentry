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
        <header className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {title && <h2 className="text-xl font-semibold text-slate-100">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
          </div>
          {right && <div className="min-w-0">{right}</div>}
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
  const neutral = type === "n_a_negative_control";
  const defended = type === "attack_failed";
  const drift = type === "rug_pull_triggered";
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <span className={`badge ${TONE[type] ?? "v-info"}`}>{VERDICT_LABEL[type] ?? type}</span>
      {!neutral && (
        <span className={`mono ${defended ? "text-good" : drift ? "text-warn" : "text-bad"}`}>
          {defended ? "防御生效" : drift ? "待确认" : "攻击成功"}
        </span>
      )}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  if (status === "done") {
    return <span className="badge v-good">完成</span>;
  }
  if (status === "error") {
    return <span className="badge v-bad">错误</span>;
  }
  if (status === "failed") {
    return <span className="badge v-bad">失败</span>;
  }
  if (status === "queued") {
    return <span className="badge v-warn">排队中</span>;
  }
  if (status === "running") {
    return <span className="badge v-warn">运行中</span>;
  }
  return <span className="badge v-warn">{status}</span>;
}

export type NoticeTone = "bad" | "warn" | "info" | "good";

const NOTICE_TONE: Record<NoticeTone, { wrap: string; title: string; body: string }> = {
  bad: { wrap: "border-rose-500/40 bg-rose-500/10", title: "text-bad", body: "text-slate-300" },
  warn: { wrap: "border-amber-500/40 bg-amber-500/10", title: "text-warn", body: "text-slate-300" },
  info: { wrap: "border-sky-500/40 bg-sky-500/10", title: "text-info", body: "text-slate-300" },
  good: { wrap: "border-emerald-500/40 bg-emerald-500/10", title: "text-good", body: "text-slate-300" },
};

/** 统一提示条：bad 用 alert 立刻打断读屏，其余用 status 温和播报。 */
export function Notice({
  tone,
  title,
  message,
  hint,
}: {
  tone: NoticeTone;
  title: ReactNode;
  message?: ReactNode;
  hint?: ReactNode;
}) {
  const t = NOTICE_TONE[tone];
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={`rounded-xl border p-4 ${t.wrap}`}>
      <div className={`text-base font-semibold ${t.title}`}>{title}</div>
      {message && <div className={`mt-2 text-sm leading-6 ${t.body}`}>{message}</div>}
      {hint && <div className="mt-2 text-sm leading-6 text-slate-400">{hint}</div>}
    </div>
  );
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
      <div className="text-sm text-slate-400">{label}</div>
      <div className={`mt-2 text-[30px] font-semibold leading-tight ${tone}`}>{value}</div>
      {hint && <div className="mt-2 text-sm leading-6 text-slate-400">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="panel text-sm text-slate-400" role="status">
      {label}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <Notice
      tone="bad"
      title="接口调用失败"
      message={<span className="mono break-all">{message}</span>}
      hint={
        <>
          后端未启动？在仓库根目录执行{" "}
          <code className="mono rounded bg-ink px-1.5 py-0.5">python -m platform_api serve</code>
          ，然后刷新本页。
        </>
      }
    />
  );
}

export function KeyValue({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-1">
          <dt className="text-sm text-slate-400">{k}</dt>
          <dd className="mono text-right text-sm text-slate-200">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function NavLink({
  path,
  active,
  children,
  "aria-current": ariaCurrent,
  onNavigate,
}: {
  path: string;
  active: boolean;
  children: ReactNode;
  "aria-current"?: "page";
  onNavigate?: () => void;
}) {
  return (
    <a
      href={href(path)}
      aria-current={ariaCurrent}
      onClick={onNavigate}
      className={`inline-flex min-h-11 items-center rounded-lg px-4 py-2 text-base transition focus-visible:ring-2 focus-visible:ring-sky-500/40 md:min-h-10 ${
        active ? "bg-sky-500/15 text-sky-100" : "text-slate-400 hover:bg-panel hover:text-slate-200"
      }`}
    >
      {children}
    </a>
  );
}
