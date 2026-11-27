import { KeyValue } from "../ui";
import { ATTACK_LABEL, type CustomDefense, type ProbeTool } from "../../types";
import ClassificationChip from "./ClassificationChip";

const INFORMED_TEXT =
  "我已了解——本次将按我声明的工具分类运行我提供的 python 命令；平台会在服务端执行该命令；sink 只落盘不出网；A3 工具描述投毒不在本次能力内。";

export default function ConfigSummaryCard({
  name,
  templateLabel,
  command,
  tools,
  sinks,
  carrierTool,
  attackClass,
  seed,
  defense,
  note,
  informed,
  onInformedChange,
}: {
  name: string;
  templateLabel: string;
  command: string[];
  tools: ProbeTool[];
  sinks: string[];
  carrierTool: string;
  attackClass: string;
  seed: number;
  defense: CustomDefense;
  note: string;
  informed: boolean;
  onInformedChange: (checked: boolean) => void;
}) {
  const hasSource = tools.some((t) => t.role === "source");
  const hasSink = sinks.length > 0;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-line bg-ink/60 p-4">
        <h3 className="text-base font-semibold text-slate-100">配置摘要</h3>
        <div className="mt-3">
          <KeyValue
            rows={[
              ["接入名称", name],
              ["模板", templateLabel],
              ["载体工具", carrierTool],
              ["攻击类", ATTACK_LABEL[attackClass] ?? attackClass],
              ["种子", String(seed)],
              ["防御档", defense === "strict" ? "严格 strict" : "标准 block"],
              ["sink 工具", sinks.join(" · ") || "未设置"],
              ["备注", note || "无"],
            ]}
          />
        </div>
      </section>

      <section className="rounded-xl border border-line bg-ink/60 p-4">
        <h3 className="text-base font-semibold text-slate-100">本次将执行的完整命令</h3>
        <pre className="mono mt-3 overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-line bg-ink p-4 leading-6 text-slate-200">
          {command.join(" ")}
        </pre>
        <p className="mt-2 text-[13px] leading-6 text-slate-400">
          平台会在服务端执行该命令；请确认命令来自你自己且参数符合预期。
        </p>
      </section>

      <section className="rounded-xl border border-line bg-ink/60 p-4">
        <h3 className="text-base font-semibold text-slate-100">工具分类确认</h3>
        <p className="mt-1 text-[13px] leading-6 text-slate-400">角色为配置标签，不是判定结果</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {tools.map((tool, index) => (
            <li key={`${tool.name}-${index}`} className="flex items-center gap-2">
              <span className="mono text-slate-300">{tool.name}</span>
              <ClassificationChip role={tool.role ?? "neutral"} />
            </li>
          ))}
        </ul>
        {!hasSource && (
          <p className="mt-3 text-[13px] leading-6 text-warn">
            至少需要把一个工具设为数据来源，污点层才有输入。
          </p>
        )}
        {!hasSink && (
          <p className="mt-3 text-[13px] leading-6 text-warn">
            至少需要把一个工具设为外发出口，判定才有落点。
          </p>
        )}
      </section>

      <label className="flex items-start gap-3 rounded-xl border border-line bg-ink/60 p-4 text-sm leading-6 text-slate-300">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 shrink-0 accent-sky-500"
          checked={informed}
          onChange={(e) => onInformedChange(e.target.checked)}
        />
        <span>{INFORMED_TEXT}</span>
      </label>
    </div>
  );
}
