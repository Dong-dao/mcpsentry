import { useRef, useState } from "react";
import { api } from "../api";
import { Notice } from "../components/ui";
import { navigate } from "../router";
import { ATTACK_LABEL, type CustomConfig, type Tier } from "../types";

const STATIC = import.meta.env.VITE_STATIC === "1";
const CLASSES = ["A1_direct_injection", "A2_indirect_tool_result", "A4_exfiltration_inducement"];
const DEFENSES = ["block", "off", "alert"];

type Form = {
  name: string;
  commandText: string;
  classesText: string;
  sinksText: string;
  carrierTool: string;
  attackClass: string;
  seed: number;
  defense: Tier;
  note: string;
};

type FieldKey = "commandText" | "name" | "classesText" | "sinksText";
type FormErrors = Partial<Record<FieldKey, string>>;

// 与 DOM 顺序一致：提交后焦点落在第一个出错的控件上。
const FIELD_ORDER: FieldKey[] = ["commandText", "name", "classesText", "sinksText"];

const INITIAL_FORM: Form = {
  name: "",
  commandText: JSON.stringify(
    ["python", "-m", "range.backend", "--profile", "t1", "--workdir", "{workdir}"],
    null,
    2,
  ),
  classesText: JSON.stringify({ read_doc: "source", send_email: "sink" }, null, 2),
  sinksText: "send_email",
  carrierTool: "read_doc",
  attackClass: CLASSES[1],
  seed: 42,
  defense: "block",
  note: "",
};

function jsonErrorLine(text: string, err: unknown): number {
  const msg = err instanceof Error ? err.message : String(err);
  const byLine = /line (\d+)/i.exec(msg);
  if (byLine) return Number(byLine[1]);
  const byPos = /position (\d+)/i.exec(msg);
  if (byPos) return text.slice(0, Number(byPos[1])).split("\n").length;
  return 1;
}

function validateCommand(text: string): string | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return `command 不是合法 JSON：请检查第 ${jsonErrorLine(text, e)} 行的引号与逗号。示例：["python","-m","server"]`;
  }
  if (!Array.isArray(parsed) || parsed.some((x) => typeof x !== "string")) {
    return 'command 必须是字符串数组。示例：["python","-m","server"]';
  }
  return null;
}

function validateClasses(text: string): string | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return `tool_classes 不是合法 JSON：请检查第 ${jsonErrorLine(text, e)} 行的引号与逗号。示例：{"read_doc":"source","send_email":"sink"}`;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return 'tool_classes 必须是对象。示例：{"read_doc":"source","send_email":"sink"}';
  }
  const illegal = Object.values(parsed).find((v) => v !== "source" && v !== "sink" && v !== "neutral");
  if (illegal !== undefined) return `工具分类只能是 source / sink / neutral，发现非法值：${String(illegal)}`;
  return null;
}

function validateField(key: FieldKey, form: Form): string | null {
  switch (key) {
    case "name":
      return form.name.trim() ? null : "请填写工具名，便于在运行台识别这次接入。";
    case "commandText":
      return validateCommand(form.commandText);
    case "classesText":
      return validateClasses(form.classesText);
    case "sinksText":
      return form.sinksText.split(/[,，\s]+/).filter(Boolean).length
        ? null
        : "至少填写一个 sink 工具，多个用逗号分隔";
  }
}

function validateAll(form: Form): FormErrors {
  const errors: FormErrors = {};
  FIELD_ORDER.forEach((key) => {
    const msg = validateField(key, form);
    if (msg) errors[key] = msg;
  });
  return errors;
}

export default function Custom() {
  const [form, setForm] = useState<Form>(INITIAL_FORM);
  const [baseline, setBaseline] = useState<Form>(INITIAL_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [exampleLoading, setExampleLoading] = useState(false);
  const [overwritePending, setOverwritePending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<{ run_id: string; target: string } | null>(null);
  const fieldRefs = useRef<Partial<Record<FieldKey, HTMLElement | null>>>({});

  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  const disabled = STATIC || busy || result !== null;

  function patch<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key as FieldKey];
      return next;
    });
  }

  function onBlur(key: FieldKey) {
    const msg = validateField(key, form);
    setErrors((prev) => {
      const next = { ...prev };
      if (msg) next[key] = msg;
      else delete next[key];
      return next;
    });
  }

  function bindField(key: FieldKey) {
    return {
      "aria-invalid": Boolean(errors[key]),
      "aria-describedby": errors[key] ? `err-${key}` : undefined,
      onBlur: () => onBlur(key),
      ref: (el: HTMLElement | null) => {
        fieldRefs.current[key] = el;
      },
    };
  }

  function errorText(key: FieldKey) {
    return errors[key] ? (
      <p id={`err-${key}`} role="alert" className="mt-2 text-sm leading-6 text-bad">
        错误：{errors[key]}
      </p>
    ) : null;
  }

  async function doFill() {
    setOverwritePending(false);
    setExampleLoading(true);
    setApiError("");
    setNotice("");
    setErrors({});
    try {
      const cfg = await api.customExample();
      const next: Form = {
        name: cfg.name,
        commandText: JSON.stringify(cfg.command, null, 2),
        classesText: JSON.stringify(cfg.tool_classes, null, 2),
        sinksText: (cfg.sinks ?? []).join(", "),
        carrierTool: cfg.carrier_tool ?? "read_doc",
        attackClass: cfg.attack_class ?? CLASSES[1],
        seed: cfg.seed ?? 42,
        defense: cfg.defense ?? "block",
        note: cfg.note ?? "",
      };
      setForm(next);
      setBaseline(next);
      setResult(null);
      setNotice("样例已填入，可以直接提交，也可以按需修改。");
    } catch (e) {
      setApiError(e instanceof Error ? e.message : String(e));
    } finally {
      setExampleLoading(false);
    }
  }

  function loadExample() {
    if (dirty) {
      setOverwritePending(true);
      return;
    }
    void doFill();
  }

  async function submit() {
    setApiError("");
    setNotice("");
    setResult(null);
    const nextErrors = validateAll(form);
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      const first = FIELD_ORDER.find((k) => nextErrors[k]);
      if (first) requestAnimationFrame(() => fieldRefs.current[first]?.focus());
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      const body: CustomConfig = {
        name: form.name.trim(),
        command: JSON.parse(form.commandText) as string[],
        tool_classes: JSON.parse(form.classesText) as Record<string, "source" | "sink" | "neutral">,
        sinks: form.sinksText
          .split(/[,，\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        carrier_tool: form.carrierTool.trim(),
        attack_class: form.attackClass,
        seed: Number(form.seed),
        defense: form.defense,
        note: form.note,
        confirm: true,
      };
      const res = await api.startCustom(body);
      setResult({ run_id: res.run_id, target: res.target });
    } catch (e) {
      setApiError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight text-slate-50 sm:text-[36px]">
            接入自己的 MCP 工具链
          </h1>
          <p className="mt-2 max-w-3xl text-base leading-7 text-slate-300">
            上传 stdio MCP server 命令与工具分类，平台用同一套攻击引擎和确定性 oracle
            跑一遍；完成后可在运行台逐组查看证据。
          </p>
        </div>
        <button className="btn" type="button" onClick={loadExample} disabled={disabled}>
          {exampleLoading ? "读取样例…" : "填入样例"}
        </button>
      </div>

      {STATIC ? (
        <Notice
          tone="info"
          title="静态演示版"
          message="静态演示版不能发起运行。请用 VITE_API_BASE 指向本地或自建后端后再接入。"
        />
      ) : (
        <Notice
          tone="info"
          title="安全提示"
          message="命令会在平台所在主机执行；请只接入你自己授权的 MCP 工具链。"
          hint={
            <>
              服务端默认关闭该能力，需显式设置{" "}
              <code className="mono rounded bg-ink px-1.5 py-0.5">MCPSENTRY_ALLOW_CUSTOM=1</code>
              。目前只接受以 python/python3 开头的命令，A3 工具描述投毒不在上传配置能力内。
            </>
          }
        />
      )}

      {overwritePending && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-sky-500/40 bg-sky-500/10 p-4 text-sm text-info">
          <span className="font-semibold">填入样例会覆盖当前已填内容</span>
          <button className="btn min-h-10 px-4 py-2 text-sm" type="button" onClick={() => void doFill()}>
            覆盖并填入
          </button>
          <button className="btn min-h-10 px-4 py-2 text-sm" type="button" onClick={() => setOverwritePending(false)}>
            取消
          </button>
        </div>
      )}
      {notice && <Notice tone="info" title="操作完成" message={notice} />}
      {apiError && <Notice tone="bad" title="接口调用失败" message={<span className="mono break-all">{apiError}</span>} />}

      {result && (
        <Notice
          tone="good"
          title="已提交，正在排队"
          message={
            <>
              运行 <span className="mono text-[13px]">{result.run_id}</span> 正在后台执行，完成后会自动出现在运行台。
            </>
          }
          hint={
            <div className="flex flex-wrap gap-3 pt-1">
              <button
                className="btn"
                type="button"
                onClick={() => navigate("/dashboard", { run: result.run_id })}
              >
                去看运行台
              </button>
              <button className="btn" type="button" onClick={() => setResult(null)}>
                修改配置再跑一次
              </button>
            </div>
          }
        />
      )}

      <fieldset disabled={disabled} className="space-y-6">
        <div className="grid gap-6 md:grid-cols-2">
          <section className="panel">
            <h2 className="border-b border-line pb-3 text-xl font-semibold text-sky-300">1 · MCP server 命令</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              JSON 字符串数组，{" "}
              <code className="mono rounded bg-ink px-1.5 py-0.5">{"{workdir}"}</code>{" "}
              会替换成本组工作目录。
            </p>
            <label className="mt-4 block text-sm font-semibold text-slate-300">
              server 命令（JSON 数组）
              <textarea
                {...bindField("commandText")}
                className={`field mono mt-2 h-44 w-full resize-y leading-5 ${errors.commandText ? "field-error" : ""}`}
                value={form.commandText}
                onChange={(e) => patch("commandText", e.target.value)}
                spellCheck={false}
              />
            </label>
            {errorText("commandText")}
            <label className="mt-4 block text-sm font-semibold text-slate-300">
              工具名
              <input
                {...bindField("name")}
                className={`field mt-2 w-full ${errors.name ? "field-error" : ""}`}
                value={form.name}
                onChange={(e) => patch("name", e.target.value)}
                placeholder="给我自己的服务起个名字"
              />
            </label>
            {errorText("name")}
            <label className="mt-4 block text-sm font-semibold text-slate-300">
              工具分类 JSON（source / sink / neutral）
              <textarea
                {...bindField("classesText")}
                className={`field mono mt-2 h-36 w-full resize-y leading-5 ${errors.classesText ? "field-error" : ""}`}
                value={form.classesText}
                onChange={(e) => patch("classesText", e.target.value)}
                spellCheck={false}
              />
            </label>
            {errorText("classesText")}
          </section>

          <section className="panel">
            <h2 className="border-b border-line pb-3 text-xl font-semibold text-sky-300">2 · 攻击与判定</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              sinks 必须是 tool_classes 里标成 sink 的工具，否则 oracle 无从判定。
            </p>
            <label className="mt-4 block text-sm font-semibold text-slate-300">
              sink 工具（多个用逗号分隔）
              <input
                {...bindField("sinksText")}
                className={`field mt-2 w-full ${errors.sinksText ? "field-error" : ""}`}
                value={form.sinksText}
                onChange={(e) => patch("sinksText", e.target.value)}
              />
            </label>
            {errorText("sinksText")}
            <label className="mt-4 block text-sm font-semibold text-slate-300">
              载体读取工具（间接注入经它进入上下文）
              <input
                className="field mt-2 w-full"
                value={form.carrierTool}
                onChange={(e) => patch("carrierTool", e.target.value)}
              />
            </label>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-semibold text-slate-300">
                攻击类
                <select
                  className="field mt-2 w-full"
                  value={form.attackClass}
                  onChange={(e) => patch("attackClass", e.target.value)}
                >
                  {CLASSES.map((c) => (
                    <option key={c} value={c}>
                      {ATTACK_LABEL[c] ?? c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-semibold text-slate-300">
                防御档
                <select
                  className="field mt-2 w-full"
                  value={form.defense}
                  onChange={(e) => patch("defense", e.target.value as Tier)}
                >
                  {DEFENSES.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-semibold text-slate-300">
                种子
                <input
                  className="field mt-2 w-full"
                  type="number"
                  value={form.seed}
                  onChange={(e) => patch("seed", Number(e.target.value))}
                />
              </label>
              <label className="block text-sm font-semibold text-slate-300">
                备注
                <input
                  className="field mt-2 w-full"
                  value={form.note}
                  onChange={(e) => patch("note", e.target.value)}
                />
              </label>
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                className="btn btn-primary min-h-[48px] w-full justify-center"
                type="button"
                onClick={submit}
                disabled={STATIC || busy}
                aria-busy={busy}
              >
                {busy ? "正在提交…" : "上传配置并运行"}
              </button>
              {!form.name.trim() && <p className="text-sm text-warn">请先填写工具名</p>}
            </div>
          </section>
        </div>
      </fieldset>
    </div>
  );
}
