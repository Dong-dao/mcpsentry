import { useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Notice } from "../components/ui";
import { navigate } from "../router";
import {
  ATTACK_LABEL,
  type CustomConfig,
  type CustomDefense,
  type ProbeTool,
  type ToolRole,
} from "../types";
import AdvancedManual, {
  type ManualDraft,
  type ManualErrors,
} from "../components/wizard/AdvancedManual";
import ConfigSummaryCard from "../components/wizard/ConfigSummaryCard";
import StepIndicator from "../components/wizard/StepIndicator";
import TemplateCard from "../components/wizard/TemplateCard";
import ToolProbeList, { type ProbeState } from "../components/wizard/ToolProbeList";
import {
  DISABLED_TEMPLATES,
  TEMPLATES,
  defaultCommand,
  toolsForTemplate,
} from "../components/wizard/templates";

const STATIC = import.meta.env.VITE_STATIC === "1";
const FALLBACK_INFO = "未匹配，已使用模板默认工具与分类，可手动调整";
const CLASSES = ["A1_direct_injection", "A2_indirect_tool_result", "A4_exfiltration_inducement"];

function inferRole(tool: ProbeTool, defaults: Array<{ name: string; role: ToolRole }>): ToolRole {
  const hit = defaults.find((d) => d.name === tool.name);
  if (hit) return hit.role;
  const text = `${tool.name} ${tool.description ?? ""}`.toLowerCase();
  if (/send|email|mail|write|post|upload|publish|submit|外发|发送|写入|上传/.test(text)) return "sink";
  if (/read|fetch|get|list|search|query|web|doc|input|读取|网页|文档|搜索/.test(text)) return "source";
  return "neutral";
}

function parseClasses(text: string): Record<string, ToolRole> {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("tool_classes 必须是对象");
  }
  const result: Record<string, ToolRole> = {};
  Object.entries(parsed).forEach(([key, value]) => {
    if (value !== "source" && value !== "sink" && value !== "neutral") {
      throw new Error(`工具 ${key} 的分类不合法`);
    }
    result[key] = value;
  });
  return result;
}

export default function Custom() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [template, setTemplate] = useState(TEMPLATES[0].id);
  const [commandText, setCommandText] = useState(defaultCommand(TEMPLATES[0].id).join(" "));
  const [tools, setTools] = useState<ProbeTool[]>(toolsForTemplate(TEMPLATES[0].id));
  const [probeState, setProbeState] = useState<ProbeState>("idle");
  const [probeInfo, setProbeInfo] = useState("");
  const [name, setName] = useState("");
  const [carrierTool, setCarrierTool] = useState("read_doc");
  const [attackClass, setAttackClass] = useState(CLASSES[1]);
  const [seed, setSeed] = useState(42);
  const [defense, setDefense] = useState<CustomDefense>("block");
  const [note, setNote] = useState("");
  const [informed, setInformed] = useState(false);
  const [stepError, setStepError] = useState("");

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advanced, setAdvanced] = useState<ManualDraft>({
    name: "",
    classesText: JSON.stringify({ read_doc: "source", send_email: "sink" }, null, 2),
    sinksText: "send_email",
    carrierTool: "read_doc",
    attackClass: CLASSES[1],
    seed: 42,
    defense: "block",
    note: "",
  });
  const [advancedErrors, setAdvancedErrors] = useState<ManualErrors>({});

  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<{ run_id: string; target: string } | null>(null);
  const probeSeq = useRef(0);

  const templateLabel = TEMPLATES.find((t) => t.id === template)?.title ?? template;
  const command = useMemo(() => {
    const trimmed = commandText.trim();
    return trimmed ? trimmed.split(/\s+/) : defaultCommand(template);
  }, [commandText, template]);
  const sinks = tools.filter((t) => t.role === "sink").map((t) => t.name);
  const hasSource = tools.some((t) => t.role === "source");
  const hasSink = sinks.length > 0;

  function patchAdvanced<K extends keyof ManualDraft>(key: K, value: ManualDraft[K]) {
    setAdvanced((prev) => ({ ...prev, [key]: value }));
    setAdvancedErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function selectTemplate(id: string) {
    setTemplate(id);
    setCommandText(defaultCommand(id).join(" "));
    setTools(toolsForTemplate(id));
    setCarrierTool(toolsForTemplate(id).find((t) => t.role === "source")?.name ?? "");
    setProbeState("idle");
    setProbeInfo("");
    setNotice("已切换模板，命令已更新为对应默认值，可再修改。");
    setResult(null);
  }

  async function loadTools() {
    const seq = ++probeSeq.current;
    const defaults = toolsForTemplate(template);
    setProbeState("loading");
    setProbeInfo("载入中…");
    setTools(defaults);
    setStepError("");
    if (STATIC) {
      setProbeState("degraded");
      setProbeInfo(FALLBACK_INFO);
      return;
    }
    try {
      const res = await api.probeCustom(command);
      if (seq !== probeSeq.current) return;
      if (!res.ok || !Array.isArray(res.tools) || res.tools.length === 0) {
        throw new Error("probe returned no tools");
      }
      const mapped: ProbeTool[] = res.tools.map((tool) => ({
        ...tool,
        role: inferRole(tool, defaults),
      }));
      const recognized = mapped.filter((tool) => tool.role !== "neutral").length;
      if (recognized === 0) {
        setTools(defaults);
        setProbeState("degraded");
        setProbeInfo(FALLBACK_INFO);
        return;
      }
      setTools(mapped);
      setCarrierTool((prev) =>
        mapped.some((tool) => tool.name === prev)
          ? prev
          : (mapped.find((tool) => tool.role === "source")?.name ?? ""),
      );
      if (recognized === mapped.length) {
        setProbeState("success");
        setProbeInfo(`已载入 ${mapped.length} 个工具，可调整分类。`);
      } else {
        setProbeState("partial");
        setProbeInfo("已载入部分工具，其余使用模板默认分类，可手动调整。");
      }
    } catch {
      if (seq !== probeSeq.current) return;
      setTools(defaults);
      setProbeState("degraded");
      setProbeInfo(FALLBACK_INFO);
    }
  }

  function goStep2() {
    if (!name.trim()) {
      setStepError("请先填写接入名称，便于在运行台识别这次接入。");
      return;
    }
    setStepError("");
    setStep(2);
    void loadTools();
  }

  function goStep3() {
    if (!hasSource || !hasSink) {
      setStepError("至少需要一项数据来源和一项外发出口，才能进入核对。");
      return;
    }
    setStepError("");
    setStep(3);
  }

  async function submit(body: CustomConfig) {
    setBusy(true);
    setApiError("");
    setNotice("");
    setResult(null);
    try {
      const res = await api.startCustom(body);
      setResult({ run_id: res.run_id, target: res.target });
    } catch (e) {
      setApiError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function runWizard() {
    if (!informed || !hasSource || !hasSink) return;
    void submit({
      name: name.trim(),
      template,
      tool_classes: Object.fromEntries(tools.map((t) => [t.name, t.role ?? "neutral"])),
      sinks,
      carrier_tool: carrierTool,
      attack_class: attackClass,
      seed: Number(seed) || 42,
      defense,
      note,
      confirm: true,
      command,
    });
  }

  function syncAdvanced() {
    setAdvanced({
      name: name.trim(),
      classesText: JSON.stringify(
        Object.fromEntries(tools.map((t) => [t.name, t.role ?? "neutral"])),
        null,
        2,
      ),
      sinksText: sinks.join(", "),
      carrierTool,
      attackClass,
      seed,
      defense,
      note,
    });
    setAdvancedErrors({});
  }

  function submitManual() {
    const errors: ManualErrors = {};
    if (!advanced.name.trim()) errors.name = "请填写工具名，便于在运行台识别这次接入。";
    let classes: Record<string, ToolRole> = {};
    try {
      classes = parseClasses(advanced.classesText);
    } catch {
      errors.classesText = "tool_classes 不是合法 JSON，请检查引号与逗号。";
    }
    const manualSinks = advanced.sinksText
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!manualSinks.length) errors.sinksText = "至少填写一个 sink 工具，多个用逗号分隔";
    setAdvancedErrors(errors);
    if (Object.keys(errors).length) return;
    void submit({
      name: advanced.name.trim(),
      template,
      tool_classes: classes,
      sinks: manualSinks,
      carrier_tool: advanced.carrierTool.trim(),
      attack_class: advanced.attackClass,
      seed: Number(advanced.seed) || 42,
      defense: advanced.defense,
      note: advanced.note,
      confirm: true,
      command,
    });
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-[30px] font-semibold leading-tight text-slate-50 sm:text-[36px]">
          真接自己的 MCP
        </h1>
        <p className="mt-2 max-w-3xl text-base leading-7 text-slate-300">
          选模板、声明工具分类、核对命令，然后运行。sink 只落盘不出网。
        </p>
      </header>

      {STATIC ? (
        <Notice
          tone="info"
          title="静态演示版"
          message="静态演示版不能发起运行。请用 VITE_API_BASE 指向本地或自建后端后再接入。"
        />
      ) : (
        <div
          role="status"
          className="rounded-xl border border-sky-500/40 bg-sky-500/10 p-3 text-[13px] leading-5 text-slate-300"
        >
          <span className="font-semibold text-info">接入说明</span>
          <span className="ml-2">
            本次填写的 python 命令会在服务端执行，请只使用你自己授权的命令。自定义接入默认关闭；未启用时请设置
            MCPSENTRY_ALLOW_CUSTOM=1。A3 工具描述投毒不在本次能力内。
          </span>
        </div>
      )}

      {notice && <Notice tone="info" title="操作完成" message={notice} />}
      {stepError && <Notice tone="warn" title="请检查配置" message={stepError} />}
      {apiError && (
        <Notice tone="bad" title="接口调用失败" message={<span className="mono break-all">{apiError}</span>} />
      )}
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
              <button className="btn" type="button" onClick={() => navigate("/dashboard", { run: result.run_id })}>
                去运行台
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setResult(null);
                  setStep(1);
                }}
              >
                改配置再跑
              </button>
            </div>
          }
        />
      )}

      <section className="flex h-[calc(100vh-320px)] min-h-[440px] max-h-[720px] flex-col overflow-hidden rounded-xl border border-line bg-panel/70 p-0">
        <StepIndicator current={step} />
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {step === 1 && (
            <div>
              <h2 className="text-xl font-semibold text-slate-100">选模板</h2>
              <p className="mt-1 text-sm leading-6 text-slate-400">
                三个模板可直接选用；其余工具面暂未开放。
              </p>
              <ul className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
                {TEMPLATES.map((t) => (
                  <TemplateCard
                    key={t.id}
                    template={t}
                    selected={template === t.id}
                    disabled={false}
                    onSelect={() => selectTemplate(t.id)}
                  />
                ))}
                {DISABLED_TEMPLATES.map((t) => (
                  <li key={t.title}>
                    <div
                      aria-disabled="true"
                      className="flex min-h-[184px] w-full flex-col rounded-xl border border-line/60 bg-ink/40 p-4 opacity-60"
                    >
                      <span className="text-base font-semibold text-slate-100">{t.title}</span>
                      <span className="mt-2 text-sm leading-6 text-slate-400">{t.description}</span>
                      <span className="mt-auto text-[13px] text-slate-400">暂未开放</span>
                    </div>
                  </li>
                ))}
              </ul>

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <label className="block text-sm font-semibold text-slate-300">
                  接入名称
                  <input
                    className="field mt-2 w-full"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="给我自己的服务起个名字"
                  />
                </label>
                <label className="block text-sm font-semibold text-slate-300">
                  防御档
                  <select
                    className="field mt-2 w-full"
                    value={defense}
                    onChange={(e) => setDefense(e.target.value as CustomDefense)}
                  >
                    <option value="block">标准 block</option>
                    <option value="strict">严格 strict</option>
                  </select>
                </label>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-3">
                <label className="block text-sm font-semibold text-slate-300">
                  攻击类
                  <select
                    className="field mt-2 w-full"
                    value={attackClass}
                    onChange={(e) => setAttackClass(e.target.value)}
                  >
                    {CLASSES.map((c) => (
                      <option key={c} value={c}>
                        {ATTACK_LABEL[c] ?? c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm font-semibold text-slate-300">
                  种子
                  <input
                    className="field mt-2 w-full"
                    type="number"
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                  />
                </label>
                <label className="block text-sm font-semibold text-slate-300">
                  备注
                  <input
                    className="field mt-2 w-full"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </div>
              <label className="mt-4 block text-sm font-semibold text-slate-300">
                自定义 python 命令
                <textarea
                  className="field mono mt-2 h-24 w-full resize-y leading-6"
                  value={commandText}
                  onChange={(e) => setCommandText(e.target.value)}
                  spellCheck={false}
                />
                <span className="mt-2 block text-[13px] font-normal leading-6 text-slate-400">
                  按空格分词；平台会在服务端执行该命令。留空则使用模板默认命令。
                </span>
              </label>
            </div>
          )}

          {step === 2 && (
            <div>
              <h2 className="text-xl font-semibold text-slate-100">确认工具</h2>
              <p className="mt-1 text-sm leading-6 text-slate-400">
                工具清单来自命令载入结果；未匹配时使用模板默认清单。分类可随时手动调整。
              </p>
              <div className="mt-4">
                <ToolProbeList
                  tools={tools}
                  probeState={probeState}
                  probeInfo={probeInfo}
                  onRoleChange={(index, role) =>
                    setTools((prev) => prev.map((t, i) => (i === index ? { ...t, role } : t)))
                  }
                  onRetry={() => void loadTools()}
                />
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <h2 className="text-xl font-semibold text-slate-100">核对并运行</h2>
              <p className="mt-1 text-sm leading-6 text-slate-400">
                核对命令与工具分类，勾选知情声明后即可提交。
              </p>
              <div className="mt-4">
                <ConfigSummaryCard
                  name={name.trim() || templateLabel}
                  templateLabel={templateLabel}
                  command={command}
                  tools={tools}
                  sinks={sinks}
                  carrierTool={carrierTool}
                  attackClass={attackClass}
                  seed={seed}
                  defense={defense}
                  note={note}
                  informed={informed}
                  onInformedChange={setInformed}
                />
              </div>
            </div>
          )}
        </div>
        <footer className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
          <button
            className="btn min-h-11 px-4 text-sm"
            type="button"
            disabled={step === 1 || busy}
            onClick={() => {
              setStepError("");
              setStep((s) => (s === 3 ? 2 : 1));
            }}
          >
            上一步
          </button>
          {!advancedOpen &&
            (step < 3 ? (
              <button
                className="btn btn-primary min-h-[48px] w-full justify-center sm:w-auto"
                type="button"
                onClick={step === 1 ? goStep2 : goStep3}
              >
                下一步
              </button>
            ) : (
              <button
                className="btn btn-primary min-h-[48px] w-full justify-center sm:w-auto"
                type="button"
                onClick={runWizard}
                disabled={STATIC || busy || !informed || !hasSource || !hasSink}
                aria-busy={busy}
              >
                {busy ? "正在提交…" : "运行"}
              </button>
            ))}
        </footer>
      </section>

      <AdvancedManual
        open={advancedOpen}
        onToggle={() => setAdvancedOpen((v) => !v)}
        draft={advanced}
        errors={advancedErrors}
        onPatch={patchAdvanced}
        onSubmit={submitManual}
        onSync={syncAdvanced}
        busy={busy}
        staticMode={STATIC}
      />
    </div>
  );
}
