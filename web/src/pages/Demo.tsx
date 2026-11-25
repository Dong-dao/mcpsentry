import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import RunDetailPanel from "../components/RunDetailPanel";
import { ErrorNote, Loading, Notice, Panel, VerdictBadge } from "../components/ui";
import { href } from "../router";
import type { DemoBundle, DemoRun } from "../types";

const TaintGraphView = lazy(() => import("../components/TaintGraph"));

/** 污点图高度随断点走：手机 240、平板 320、宽屏 360，不横向溢出。 */
function useGraphHeight() {
  const pick = () => (window.innerWidth >= 1280 ? 360 : window.innerWidth >= 768 ? 320 : 240);
  const [height, setHeight] = useState(pick);
  useEffect(() => {
    const onResize = () => setHeight(pick());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return height;
}

/**
 * 一键 demo：读 `/api/demo/preset` 的预置包——同一格 off/block 的真实成对运行，
 * 评委零门槛、不占算力；ECS 冷启动或算力被占时这一页依然有完整内容。
 */
export default function Demo() {
  const [bundle, setBundle] = useState<DemoBundle | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<DemoRun | null>(null);
  const [launching, setLaunching] = useState(false);
  const [launched, setLaunched] = useState("");
  const staticMode = import.meta.env.VITE_STATIC === "1";
  const graphHeight = useGraphHeight();

  const load = useCallback(() => {
    api
      .demoPreset()
      .then(setBundle)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  if (error) {
    return (
      <ErrorNote
        message={`${error}\n预置包缺失时先跑一次：python -m platform_api build-demo（会真跑一组 off/block 对）。`}
      />
    );
  }
  if (!bundle) return <Loading label="读取预置 demo 包…" />;

  const off = bundle.runs.find((r) => r.defense === "off");
  const block = bundle.runs.find((r) => r.defense === "block");

  const runLive = async () => {
    setLaunching(true);
    setLaunched("");
    try {
      const res = await api.startDemo({
        target: bundle.cell.target,
        attack_class: bundle.cell.attack_class,
        seed: bundle.cell.seed,
        defense: "block",
        note: "来自一键 demo 页的现场复跑",
      });
      setLaunched(res.runs.map((r) => r.run_id).join(" · "));
    } catch (e) {
      setError(String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="space-y-5">
      <Panel
        title={bundle.title}
        subtitle={`预置生成于 ${bundle.generated_at} · engine ${bundle.engine_version} · seed ${bundle.cell.seed}`}
        right={
          <div className="flex flex-wrap items-center gap-2">
            <a className="btn" href={href("/dashboard")}>
              看全部运行
            </a>
            <button
              className="btn btn-primary"
              onClick={runLive}
              disabled={launching || staticMode}
              aria-busy={launching}
              title={
                staticMode ? "静态演示版：现场复跑需本地部署（python -m platform_api serve）" : undefined
              }
            >
              {launching ? "排队中…" : (
                <>
                  <span className="sm:hidden">{staticMode ? "静态版不可复跑" : "现场复跑一对"}</span>
                  <span className="hidden sm:inline">
                    {staticMode ? "静态演示版（复跑需本地部署）" : "现场复跑一对"}
                  </span>
                </>
              )}
            </button>
          </div>
        }
      >
        <p className="text-sm leading-6 text-slate-300">{bundle.narrative.reading}</p>
        {launched && (
          <div className="mt-4">
            <Notice
              tone="info"
              title="已提交现场复跑"
              message={<span className="mono break-all">{launched}</span>}
              hint={
                <a href={href("/dashboard")} className="text-info underline decoration-sky-500/40 hover:text-sky-200">
                  去看运行台 →
                </a>
              }
            />
          </div>
        )}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        {[off, block].map((run, i) =>
          run ? (
            <Panel
              key={run.run_id}
              title={
                <span className="flex flex-wrap items-center gap-3">
                  <span className={i === 0 ? "text-bad" : "text-good"}>
                    防御 {run.defense === "off" ? "关闭" : "开启"}
                  </span>
                  <VerdictBadge type={run.verdict?.type} />
                </span>
              }
              subtitle={run.narrative}
              right={
                <button className="btn" onClick={() => setOpen(open?.run_id === run.run_id ? null : run)}>
                  {open?.run_id === run.run_id ? "收起详情" : "展开完整报告"}
                </button>
              }
            >
              {i === 0 ? <OffSummary run={run} /> : <BlockSummary run={run} />}
              {/* 折叠态也要有图：污点传播图是这一页的主角，不该藏在按钮后面 */}
              {open?.run_id === run.run_id ? null : (
                <div className="mt-4">
                  <Suspense fallback={<Loading label="加载污点传播图…" />}>
                    <TaintGraphView graph={run.graph} height={graphHeight} />
                  </Suspense>
                  <p className="mono mt-2 text-sm leading-6 text-slate-400">
                    绿边 = 代理拦下的污点边，红线 = 载荷真的送达后端；每个调用点是一格（r = 轮次），可拖动缩放。
                  </p>
                </div>
              )}
              {open?.run_id === run.run_id && (
                <div className="mt-4 border-t border-line pt-4">
                  <RunDetailPanel detail={run} />
                  <details className="mt-4">
                    <summary className="mono cursor-pointer text-sm text-slate-400">
                      导出的 Markdown 原文（点 /api/runs/{run.run_id}/export?format=md 可下载）
                    </summary>
                    <pre className="mono mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-ink p-3 text-slate-400">
                      {run.markdown}
                    </pre>
                  </details>
                </div>
              )}
            </Panel>
          ) : null,
        )}
      </div>

      <p className="text-sm text-slate-400">{bundle.compliance}</p>
    </div>
  );
}

function RunStats({ run }: { run: DemoRun }) {
  return (
    <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {[
        ["判定", run.verdict?.type ?? "—"],
        ["攻击成功", String(run.verdict?.success)],
        ["证据", run.verdict?.evidence?.slice(0, 64) ?? "—"],
        ["轮次", `${run.meta?.rounds_used} / ${run.config?.attack?.max_rounds}`],
        ["污点边", String(run.report?.taint_edges?.length ?? 0)],
        ["sink 捕获", String(run.sink_capture?.length ?? 0)],
      ].map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-1">
          <dt className="text-sm text-slate-400">{k}</dt>
          <dd className="mono text-right text-slate-200">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function OffSummary({ run }: { run: DemoRun }) {
  const captured = run.sink_capture[0];
  return (
    <>
      <div className="mt-2 rounded-lg border border-bad/40 bg-rose-500/10 p-4">
        <div className="text-sm text-slate-400">send_email 实际发出去的内容（节选）</div>
        <pre className="mono mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-bad">
          {captured ? String((captured.payload as Record<string, unknown>).body ?? JSON.stringify(captured.payload)) : "（无捕获）"}
        </pre>
      </div>
      <RunStats run={run} />
    </>
  );
}

function BlockSummary({ run }: { run: DemoRun }) {
  const first = run.report?.taint_edges?.[0];
  return (
    <>
      <div className="mt-2 rounded-lg border border-good/40 bg-emerald-500/10 p-4">
        <div className="text-sm text-slate-400">代理拦下的第一条污点边</div>
        <pre className="mono mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-good">
          {first
            ? `${first.source_tool} → ${first.sink_tool}.${first.sink_field}  layer=${first.layer}  blocked=${first.blocked}\n${first.matched_snippet}`
            : "（无污点边）"}
        </pre>
      </div>
      <RunStats run={run} />
    </>
  );
}
