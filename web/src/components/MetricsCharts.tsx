import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricsPayload } from "../types";
import { ATTACK_LABEL } from "../types";

const OFF = "#ff8fa3";
const ON = "#7ee2b8";
const AXIS = { fontSize: 13, fill: "#8b93a7" } as const;
const TOOLTIP = {
  contentStyle: { background: "#151922", border: "1px solid #262b36", borderRadius: 8, fontSize: 13 },
  labelStyle: { color: "#e6e8ee" },
} as const;
const LEGEND = { fontSize: 13 } as const;

const asPercent = (v: number) => `${(v * 100).toFixed(0)}%`;

/** 靶标级 ASR：off 与 block 并排，就是"这套防御在这个靶标上的净效果"。 */
export function AsrByTargetChart({ metrics, height = 240 }: { metrics: MetricsPayload; height?: number }) {
  const ids = Object.keys(metrics.asr_by_target.off);
  const data = ids.map((id) => ({
    id,
    off: metrics.asr_by_target.off[id]?.asr ?? 0,
    block: metrics.asr_by_target.block[id]?.asr ?? 0,
    runs: metrics.asr_by_target.off[id]?.runs ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="#20263a" vertical={false} />
        <XAxis dataKey="id" tick={AXIS} axisLine={{ stroke: "#262b36" }} tickLine={false} />
        <YAxis domain={[0, 1]} tick={AXIS} tickFormatter={asPercent} axisLine={false} tickLine={false} />
        <Tooltip {...TOOLTIP} formatter={(v: number) => asPercent(v)} />
        <Legend wrapperStyle={LEGEND} />
        <Bar dataKey="off" name="防御 off" fill={OFF} radius={[4, 4, 0, 0]} />
        <Bar dataKey="block" name="防御 block" fill={ON} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 防御有效性（ASR_off − ASR_block）：负值说明这一档防御把攻击打回零以下，理论上不可能。 */
export function EffectivenessChart({ metrics, height = 240 }: { metrics: MetricsPayload; height?: number }) {
  const data = Object.entries(metrics.effectiveness_applicable_only).map(([cls, row]) => ({
    cls: ATTACK_LABEL[cls] ?? cls,
    delta: row.delta,
    off: row.off.asr,
    on: row.on.asr,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 60 }}>
        <CartesianGrid stroke="#20263a" horizontal={false} />
        <XAxis type="number" domain={[0, 1]} tick={AXIS} tickFormatter={asPercent} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="cls" width={140} tick={AXIS} axisLine={{ stroke: "#262b36" }} tickLine={false} />
        <Tooltip {...TOOLTIP} formatter={(v: number, name: string) => [asPercent(v), name]} />
        <ReferenceLine
          x={0.8}
          stroke="#a9c6ff"
          strokeDasharray="4 4"
          label={{ value: "目标 ≥80%", fontSize: 13, fill: "#a9c6ff", position: "top" }}
        />
        <Bar dataKey="delta" name="有效性（仅适用格）" radius={[0, 4, 4, 0]}>
          {data.map((d) => (
            <Cell key={d.cls} fill={d.delta >= 0.8 ? ON : "#ffd08a"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 代理延迟开销：配对比较 off/on 的 p50、p95 差值（毫秒）。 */
export function LatencyChart({ metrics, height = 280 }: { metrics: MetricsPayload; height?: number }) {
  const data = metrics.latency_overhead.rows.map((r) => ({
    key: `${r.target} ${r.attack_class.split("_")[0]} s${r.seed}`,
    p50: r.p50_delta_ms,
    p95: r.p95_delta_ms,
  }));
  if (!data.length) return <p className="text-sm text-slate-400">暂无 off/on 配对的延迟样本。</p>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
        <CartesianGrid stroke="#20263a" vertical={false} />
        <XAxis
          dataKey="key"
          tick={{ ...AXIS, fontSize: 12 }}
          axisLine={{ stroke: "#262b36" }}
          tickLine={false}
          interval={Math.max(0, Math.ceil(data.length / 10) - 1)}
          angle={-30}
          height={64}
          textAnchor="end"
        />
        <YAxis tick={AXIS} unit="ms" axisLine={false} tickLine={false} />
        <Tooltip {...TOOLTIP} formatter={(v: number, name: string) => [`${v} ms`, name]} />
        <Legend wrapperStyle={LEGEND} />
        <ReferenceLine
          y={50}
          stroke="#ff8fa3"
          strokeDasharray="4 4"
          label={{ value: "p95 目标 <50ms", fontSize: 13, fill: "#ff8fa3", position: "insideTopRight" }}
        />
        <Bar dataKey="p50" name="Δp50" fill="#a9c6ff" radius={[3, 3, 0, 0]} />
        <Bar dataKey="p95" name="Δp95" fill="#7ee2b8" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
