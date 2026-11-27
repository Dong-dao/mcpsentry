const LABELS = ["选模板", "确认工具", "核对并运行"] as const;

export default function StepIndicator({ current }: { current: 1 | 2 | 3 }) {
  return (
    <nav aria-label="接入步骤" className="border-b border-line px-6 py-4">
      <ol className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {LABELS.map((label, index) => {
          const step = (index + 1) as 1 | 2 | 3;
          const state = step < current ? "done" : step === current ? "current" : "future";
          const tone =
            state === "done"
              ? "text-good"
              : state === "current"
                ? "text-sky-300"
                : "text-slate-500";
          return (
            <li
              key={label}
              aria-current={state === "current" ? "step" : undefined}
              className={`flex items-center gap-2 text-[13px] ${tone}`}
            >
              <span className="mono" aria-hidden="true">
                {String(step).padStart(2, "0")}
              </span>
              <span className={state === "current" ? "font-semibold" : undefined}>{label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
