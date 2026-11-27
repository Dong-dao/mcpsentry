import DimensionBreakdown from "./DimensionBreakdown";
import Gauge from "./Gauge";
import type { ScoreResult } from "./rules";

export default function ShareableScoreCard({
  result,
  configLabel,
}: {
  result: ScoreResult;
  configLabel?: string;
}) {
  return (
    <article className="w-[720px] max-w-full rounded-xl border border-line bg-panel p-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">MCP 配置安全体检</h2>
          <p className="mt-1 text-sm text-slate-400">{configLabel || "本地配置"}</p>
        </div>
        <span className="mono text-slate-500">规则版</span>
      </header>

      <div className="mt-6 grid gap-6 md:grid-cols-[240px_1fr]">
        <Gauge score={result.total} />
        <DimensionBreakdown dimensions={result.dimensions} />
      </div>

      <p className="mt-6 text-sm leading-6 text-slate-200">{result.summary}</p>
      <p className="mt-6 border-t border-line pt-4 text-[13px] text-slate-400">
        本地规则计算，不代表动态攻击验证结果
      </p>
    </article>
  );
}
