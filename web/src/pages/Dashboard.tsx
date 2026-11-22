import { useCallback, useEffect, useState } from "react";
import { api, type RunFilter } from "../api";
import RunDetailPanel from "../components/RunDetailPanel";
import { ErrorNote, Loading, Panel, StatusBadge, VerdictBadge } from "../components/ui";
import { navigate, useRoute } from "../router";
import type { RunDetail, RunRow, TargetsResponse, Tier } from "../types";
import { ATTACK_LABEL } from "../types";

const PAGE = 50;

interface FormState {
  target: string;
  attack_class: string;
  seed: number;
  defense: string;
  paraphrase: boolean;
  semantic: boolean;
  note: string;
}

export default function Dashboard() {
  const route = useRoute();
  const selected = route.query.get("run") ?? "";

  const [registry, setRegistry] = useState<TargetsResponse | null>(null);
  const [filter, setFilter] = useState<RunFilter>({});
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<{ items: RunRow[]; total: number } | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState<FormState>({
    target: "T1",
    attack_class: "A2_indirect_tool_result",
    seed: 42,
    defense: "block",
    paraphrase: false,
    semantic: false,
    note: "",
  });
  const [confirmMatrix, setConfirmMatrix] = useState(false);
  const [message, setMessage] = useState("");

  const loadRuns = useCallback(async () => {
    const res = await api.runs({ ...filter, limit: PAGE, offset });
    setPage({ items: res.items, total: res.stats.runs });
  }, [filter, offset]);

  useEffect(() => {
    api.targets().then(setRegistry).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    loadRuns().catch((e: Error) => setError(e.message));
  }, [loadRuns]);

  useEffect(() => {
    if (!selected) return setDetail(null);
    setDetail(null);
    api.run(selected).then(setDetail).catch((e: Error) => setError(e.message));
  }, [selected]);

  // 有排队/执行中的运行时才轮询，空页面不打后端
  const pending = page?.items.some((r) => r.status === "queued" || r.status === "running");
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => {
      loadRuns().catch(() => undefined);
      if (selected) api.run(selected).then(setDetail).catch(() => undefined);
    }, 4000);
    return () => clearInterval(t);
  }, [pending, loadRuns, selected]);

  const startRun = async () => {
    setError("");
    setMessage("");
    try {
      const res = await api.startRun({ ...form, seed: Number(form.seed), defense: form.defense as Tier });
      setMessage(`已提交 ${res.run_id}，后台执行中（2 核机器上会排队）`);
      navigate("/dashboard", { run: res.run_id });
      await loadRuns();
    } catch (e) {
      setError(String(e));
    }
  };

  const startMatrix = async () => {
    setError("");
    try {
      const res = await api.startMatrix({
        targets: [form.target],
        classes: [form.attack_class],
        seeds: registry?.seeds ?? [42],
        tiers: ["off", "block"],
        confirm: true,
      });
      setMessage(`已提交 ${res.cells} 格批量运行（off/block × ${registry?.seeds.length ?? 3} 个种子）`);
      await loadRuns();
    } catch (e) {
      setError(String(e));
    }
  };

  const applicable = registry?.targets.find((t) => t.id === form.target)?.applicable ?? [];

  return (
    <div className="space-y-4">
      {error && <ErrorNote message={error} />}

      <Panel
        title="发起运行"
        subtitle="写接口是算力开关：一次运行 = 一次真实攻击投放，跑完自动进历史"
        right={
          <div className="flex items-center gap-3">
            <label className="mono flex items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={confirmMatrix}
                onChange={(e) => setConfirmMatrix(e.target.checked)}
              />
              允许批量跑格
            </label>
            <button className="btn px-3 py-1 text-xs" onClick={startMatrix} disabled={!confirmMatrix}>
              跑这一格的全矩阵
            </button>
            <button className="btn btn-primary px-3 py-1 text-xs" onClick={startRun}>
              运行单格
            </button>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <label className="text-xs text-slate-400">
            靶标
            <select
              className="field mt-1"
              value={form.target}
              onChange={(e) => {
                const target = e.target.value;
                const app = registry?.targets.find((t) => t.id === target)?.applicable ?? [];
                setForm({ ...form, target, attack_class: app[0] ?? form.attack_class });
              }}
            >
              {registry?.targets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            攻击类
            <select
              className="field mt-1"
              value={form.attack_class}
              onChange={(e) => setForm({ ...form, attack_class: e.target.value })}
            >
              {(applicable.length ? applicable : registry?.attack_classes ?? []).map((c) => (
                <option key={c} value={c}>
                  {ATTACK_LABEL[c] ?? c}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            种子
            <select className="field mt-1" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })}>
              {(registry?.seeds ?? [42, 43, 44]).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            防御档
            <select className="field mt-1" value={form.defense} onChange={(e) => setForm({ ...form, defense: e.target.value })}>
              <option value="off">off（直连后端）</option>
              <option value="block">block（代理拦截）</option>
              <option value="alert">alert（只告警放行）</option>
            </select>
          </label>
          <label className="text-xs text-slate-400">
            备注
            <input
              className="field mt-1"
              value={form.note}
              placeholder="写进历史，方便回来看"
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          <div className="flex flex-col justify-end gap-1 text-xs text-slate-400">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={form.paraphrase}
                onChange={(e) => setForm({ ...form, paraphrase: e.target.checked })}
              />
              改写变体（消融）
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-sky-500"
                checked={form.semantic}
                onChange={(e) => setForm({ ...form, semantic: e.target.checked })}
              />
              语义层（需 API key）
            </label>
          </div>
        </div>
        {message && <p className="mono mt-3 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs text-info">{message}</p>}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <Panel
          title={`运行历史${page ? ` · ${page.total} 组` : ""}`}
          subtitle="矩阵正式产物、平台临时运行、批量跑格都在这一张表里"
          right={
            <div className="flex items-center gap-2 text-xs">
              <select
                className="field w-auto py-1 text-xs"
                value={filter.target ?? ""}
                onChange={(e) => {
                  setOffset(0);
                  setFilter({ ...filter, target: e.target.value || undefined });
                }}
              >
                <option value="">全部靶标</option>
                {registry?.targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.id}
                  </option>
                ))}
              </select>
              <select
                className="field w-auto py-1 text-xs"
                value={filter.defense ?? ""}
                onChange={(e) => {
                  setOffset(0);
                  setFilter({ ...filter, defense: e.target.value || undefined });
                }}
              >
                <option value="">全部防御</option>
                <option value="off">off（无防御）</option>
                <option value="on">on（代理，含 block/alert）</option>
              </select>
            </div>
          }
        >
          {!page ? (
            <Loading label="读取历史索引…" />
          ) : (
            <>
              <div className="max-h-[560px] overflow-auto">
                <table className="w-full">
                  <thead className="sticky top-0 bg-panel">
                    <tr>
                      <th className="th">运行</th>
                      <th className="th w-24">判定</th>
                      <th className="th w-20">状态</th>
                      <th className="th w-16">轮次</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((r) => (
                      <tr
                        key={r.run_id}
                        onClick={() => navigate("/dashboard", { run: r.run_id })}
                        className={`cursor-pointer transition hover:bg-ink/60 ${
                          selected === r.run_id ? "bg-sky-500/10" : ""
                        }`}
                      >
                        <td className="td">
                          <div className="mono truncate text-slate-200">{r.run_id}</div>
                          <div className="mono text-[11px] text-slate-500">
                            {r.target} · {ATTACK_LABEL[r.attack_class] ?? r.attack_class} · {r.defense} · seed {r.seed}
                            {r.note ? ` · ${r.note}` : ""}
                          </div>
                        </td>
                        <td className="td">
                          <VerdictBadge type={r.verdict} />
                        </td>
                        <td className="td">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="td mono text-slate-400">{r.rounds_used ?? "—"}</td>
                      </tr>
                    ))}
                    {!page.items.length && (
                      <tr>
                        <td className="td text-slate-400" colSpan={4}>
                          没有匹配的运行。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                <button className="btn px-3 py-1 text-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  上一页
                </button>
                <span className="mono">
                  {offset + 1}–{Math.min(offset + PAGE, page.total)} / {page.total}
                </span>
                <button className="btn px-3 py-1 text-xs" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>
                  下一页
                </button>
              </div>
            </>
          )}
        </Panel>

        {selected ? detail ? <RunDetailPanel detail={detail} /> : <Loading label={`读取 ${selected} 的产物…`} /> : (
          <Panel title="详情" subtitle="点左侧任意一行，或从一键 demo 进入">
            <p className="text-sm text-slate-400">
              这里会展开判定证据、污点传播图、攻击轨迹、sink 捕获与修复建议——全部来自该组运行的原始产物文件。
            </p>
          </Panel>
        )}
      </div>
    </div>
  );
}
