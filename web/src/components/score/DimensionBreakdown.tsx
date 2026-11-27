import type { ScoreDimension } from "./rules";
import DiagnosisLine from "./DiagnosisLine";

function fillFor(score: number): string {
  if (score >= 90) return "bg-good";
  if (score >= 70) return "bg-info";
  if (score >= 40) return "bg-warn";
  return "bg-bad";
}

export default function DimensionBreakdown({ dimensions }: { dimensions: ScoreDimension[] }) {
  return (
    <div>
      <p className="text-[13px] leading-6 text-slate-400">70% 参考线：越靠右约束越充分</p>
      <ul className="mt-3 space-y-4">
        {dimensions.map((d) => (
          <li key={d.key}>
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="text-slate-200">{d.label}</span>
              <span className="mono text-slate-200">{d.score}/100</span>
            </div>
            <div className="relative mt-2 h-3 w-full rounded-full bg-ink" aria-hidden="true">
              <div
                className={`h-3 rounded-full ${fillFor(d.score)}`}
                style={{ width: `${d.score}%` }}
              />
              <div className="absolute -top-0.5 h-4 w-px bg-slate-500" style={{ left: "70%" }} />
            </div>
            <DiagnosisLine text={d.diagnosis} />
          </li>
        ))}
      </ul>
    </div>
  );
}
