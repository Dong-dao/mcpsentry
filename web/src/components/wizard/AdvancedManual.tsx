import { ATTACK_LABEL, type CustomDefense } from "../../types";

export interface ManualDraft {
  name: string;
  classesText: string;
  sinksText: string;
  carrierTool: string;
  attackClass: string;
  seed: number;
  defense: CustomDefense;
  note: string;
}

export type ManualErrors = Partial<Record<keyof ManualDraft, string>>;

const CLASSES = ["A1_direct_injection", "A2_indirect_tool_result", "A4_exfiltration_inducement"];

export default function AdvancedManual({
  open,
  onToggle,
  draft,
  errors,
  onPatch,
  onSubmit,
  onSync,
  busy,
  staticMode,
}: {
  open: boolean;
  onToggle: () => void;
  draft: ManualDraft;
  errors: ManualErrors;
  onPatch: <K extends keyof ManualDraft>(key: K, value: ManualDraft[K]) => void;
  onSubmit: () => void;
  onSync: () => void;
  busy: boolean;
  staticMode: boolean;
}) {
  return (
    <section className="panel">
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-3 text-left text-base font-semibold text-slate-100"
        aria-expanded={open}
        aria-controls="advanced-manual-body"
        onClick={onToggle}
      >
        <span>高级 / 手动配置</span>
        <span className="mono text-slate-400">{open ? "收起" : "展开"}</span>
      </button>
      <p className="mt-1 text-sm leading-6 text-slate-400">
        直接编辑工具分类 JSON 与 sink 列表。展开后向导底部的主按钮隐藏，这里成为唯一提交入口。
      </p>

      {open && (
        <div id="advanced-manual-body" className="mt-4 space-y-4 border-t border-line pt-4">
          <div className="flex flex-wrap gap-3">
            <button className="btn min-h-10 px-4 py-2 text-sm" type="button" onClick={onSync}>
              用当前向导配置填入
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-semibold text-slate-300">
              接入名称
              <input
                className={`field mt-2 w-full ${errors.name ? "field-error" : ""}`}
                value={draft.name}
                onChange={(e) => onPatch("name", e.target.value)}
              />
              {errors.name && (
                <span className="mt-2 block text-[13px] leading-6 text-bad" role="alert">
                  {errors.name}
                </span>
              )}
            </label>
            <label className="block text-sm font-semibold text-slate-300">
              sink 工具（多个用逗号分隔）
              <input
                className={`field mt-2 w-full ${errors.sinksText ? "field-error" : ""}`}
                value={draft.sinksText}
                onChange={(e) => onPatch("sinksText", e.target.value)}
              />
              {errors.sinksText && (
                <span className="mt-2 block text-[13px] leading-6 text-bad" role="alert">
                  {errors.sinksText}
                </span>
              )}
            </label>
          </div>
          <label className="block text-sm font-semibold text-slate-300">
            工具分类 JSON（source / sink / neutral）
            <textarea
              className={`field mono mt-2 h-36 w-full resize-y leading-5 ${errors.classesText ? "field-error" : ""}`}
              value={draft.classesText}
              onChange={(e) => onPatch("classesText", e.target.value)}
              spellCheck={false}
            />
            {errors.classesText && (
              <span className="mt-2 block text-[13px] leading-6 text-bad" role="alert">
                {errors.classesText}
              </span>
            )}
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-semibold text-slate-300">
              载体读取工具
              <input
                className="field mt-2 w-full"
                value={draft.carrierTool}
                onChange={(e) => onPatch("carrierTool", e.target.value)}
              />
            </label>
            <label className="block text-sm font-semibold text-slate-300">
              攻击类
              <select
                className="field mt-2 w-full"
                value={draft.attackClass}
                onChange={(e) => onPatch("attackClass", e.target.value)}
              >
                {CLASSES.map((c) => (
                  <option key={c} value={c}>
                    {ATTACK_LABEL[c] ?? c}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-semibold text-slate-300">
              防御档
              <select
                className="field mt-2 w-full"
                value={draft.defense}
                onChange={(e) => onPatch("defense", e.target.value as CustomDefense)}
              >
                <option value="block">标准 block</option>
                <option value="strict">严格 strict</option>
              </select>
            </label>
            <label className="block text-sm font-semibold text-slate-300">
              种子
              <input
                className="field mt-2 w-full"
                type="number"
                value={draft.seed}
                onChange={(e) => onPatch("seed", Number(e.target.value))}
              />
            </label>
          </div>
          <label className="block text-sm font-semibold text-slate-300">
            备注
            <input
              className="field mt-2 w-full"
              value={draft.note}
              onChange={(e) => onPatch("note", e.target.value)}
            />
          </label>
          <button
            className="btn btn-primary min-h-[48px] w-full justify-center"
            type="button"
            onClick={onSubmit}
            disabled={staticMode || busy}
            aria-busy={busy}
          >
            {busy ? "正在提交…" : "上传配置并运行"}
          </button>
        </div>
      )}
    </section>
  );
}
