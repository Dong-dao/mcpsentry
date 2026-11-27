import { tierFor } from "./rules";

/** 色值取自 tailwind.config.js 既有语义色，不新增色相。 */
const TIERS = [
  { range: "0–39", label: "风险较高", color: "#ff8fa3" },
  { range: "40–69", label: "需要修补", color: "#ffd08a" },
  { range: "70–89", label: "基本可用", color: "#a9c6ff" },
  { range: "90–100", label: "较稳", color: "#7ee2b8" },
];

const RADIUS = 100;
const CENTER_X = 120;
const CENTER_Y = 130;
const ARC_LENGTH = Math.PI * RADIUS;
const BOUNDARIES = [0, 39, 69, 89, 100];

function colorFor(score: number): string {
  if (score >= 90) return TIERS[3].color;
  if (score >= 70) return TIERS[2].color;
  if (score >= 40) return TIERS[1].color;
  return TIERS[0].color;
}

function tick(boundary: number, radius: number): { x: number; y: number } {
  const angle = Math.PI - (boundary / 100) * Math.PI;
  return {
    x: CENTER_X + radius * Math.cos(angle),
    y: CENTER_Y - radius * Math.sin(angle),
  };
}

export default function Gauge({ score }: { score: number }) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const tier = tierFor(value);
  return (
    <div>
      <svg
        viewBox="0 0 240 150"
        className="w-full max-w-[240px]"
        role="img"
        aria-label={`安全体检总分 ${value} 分，满分 100 分，档位 ${tier}`}
      >
        <path
          d="M 20 130 A 100 100 0 0 1 220 130"
          fill="none"
          stroke="#262b36"
          strokeWidth="14"
          strokeLinecap="round"
        />
        <path
          d="M 20 130 A 100 100 0 0 1 220 130"
          fill="none"
          stroke={colorFor(value)}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${(value / 100) * ARC_LENGTH} ${ARC_LENGTH}`}
        />
        {BOUNDARIES.map((boundary) => {
          const inner = tick(boundary, 92);
          const outer = tick(boundary, 110);
          return (
            <line
              key={boundary}
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              stroke="#64748b"
              strokeWidth="2"
            />
          );
        })}
        <text x="120" y="104" textAnchor="middle" fontSize="48" fontWeight="600" fill="#f8fafc">
          {value}
        </text>
        <text x="120" y="124" textAnchor="middle" fontSize="13" fill="#94a3b8">
          /100
        </text>
        <text x="120" y="146" textAnchor="middle" fontSize="13" fill="#cbd5e1">
          {tier}
        </text>
      </svg>
      <ul className="mt-3 space-y-1 text-[13px] leading-5 text-slate-400">
        {TIERS.map((t) => (
          <li key={t.label} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="h-2 w-4 shrink-0 rounded-sm"
              style={{ backgroundColor: t.color }}
            />
            <span className="mono whitespace-nowrap">{t.range}</span>
            <span className="whitespace-nowrap">{t.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
