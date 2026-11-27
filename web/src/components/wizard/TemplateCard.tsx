import type { TemplateDef } from "./templates";

export default function TemplateCard({
  template,
  selected,
  disabled,
  onSelect,
}: {
  template: TemplateDef;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        aria-pressed={selected}
        onClick={onSelect}
        className={`flex min-h-[184px] w-full flex-col rounded-xl border p-4 text-left transition ${
          disabled
            ? "cursor-not-allowed border-line/60 bg-ink/40 opacity-60"
            : selected
              ? "border-sky-500/70 bg-sky-500/10"
              : "border-line bg-ink/60 hover:border-sky-500/60"
        }`}
      >
        <span className="mono text-slate-500">{template.id}</span>
        <span className="mt-2 text-base font-semibold text-slate-100">{template.title}</span>
        <span className="mt-2 text-sm leading-6 text-slate-400">{template.description}</span>
        <span className="mono mt-auto pt-3 text-slate-500">
          {Object.keys(template.tools).join(" · ")}
        </span>
      </button>
    </li>
  );
}
