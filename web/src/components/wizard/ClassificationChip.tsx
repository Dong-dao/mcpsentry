import type { ToolRole } from "../../types";

const LABEL: Record<ToolRole, string> = {
  source: "数据来源",
  sink: "外发出口",
  neutral: "普通工具",
};

const BAR: Record<ToolRole, string> = {
  source: "border-l-warn",
  sink: "border-l-bad",
  neutral: "border-l-slate-400",
};

export default function ClassificationChip({ role }: { role: ToolRole }) {
  return (
    <span className={`chip-role ${BAR[role]}`}>
      <span>{LABEL[role]}</span>
      <span className="mono text-slate-400">{role}</span>
    </span>
  );
}
