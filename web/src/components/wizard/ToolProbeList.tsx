import type { ProbeTool, ToolRole } from "../../types";
import ClassificationChip from "./ClassificationChip";

export type ProbeState = "idle" | "loading" | "success" | "partial" | "degraded";

const ROLE_OPTIONS: Array<{ value: ToolRole; label: string }> = [
  { value: "source", label: "数据来源 source" },
  { value: "sink", label: "外发出口 sink" },
  { value: "neutral", label: "普通工具 neutral" },
];

export default function ToolProbeList({
  tools,
  probeState,
  probeInfo,
  onRoleChange,
  onRetry,
}: {
  tools: ProbeTool[];
  probeState: ProbeState;
  probeInfo: string;
  onRoleChange: (index: number, role: ToolRole) => void;
  onRetry: () => void;
}) {
  return (
    <div>
      <p className="text-[13px] leading-6 text-slate-400">角色为配置标签，不是判定结果</p>
      <div
        role="status"
        aria-live="polite"
        className={`mt-2 rounded-lg border px-3 py-2 text-[13px] leading-6 ${
          probeState === "degraded" || probeState === "partial"
            ? "border-sky-500/40 bg-sky-500/10 text-info"
            : "border-line bg-ink/60 text-slate-400"
        }`}
      >
        {probeInfo || "载入中…"}
      </div>

      {tools.length === 0 ? (
        <p className="mt-4 text-[13px] leading-6 text-slate-400">
          暂无工具，请返回上一步重新选择模板。
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {tools.map((tool, index) => {
            const role: ToolRole = tool.role ?? "neutral";
            return (
              <li
                key={`${tool.name}-${index}`}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-ink/60 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="mono break-all text-slate-100">{tool.name}</div>
                  {tool.description && (
                    <div className="mt-1 text-[13px] leading-5 text-slate-400">
                      {tool.description}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ClassificationChip role={role} />
                  <select
                    className="field-sm"
                    aria-label={`设置工具 ${tool.name} 的分类`}
                    value={role}
                    onChange={(e) => onRoleChange(index, e.target.value as ToolRole)}
                  >
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-4">
        <button className="btn min-h-10 px-4 py-2 text-sm" type="button" onClick={onRetry}>
          重新载入
        </button>
      </div>
    </div>
  );
}
