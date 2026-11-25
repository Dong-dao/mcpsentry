import "@xyflow/react/dist/style.css";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { EdgeState, GraphEdge, GraphNode, TaintGraph } from "../types";
import { EDGE_LABEL } from "../types";

// 列 = 角色（攻击者 / Agent / 污点源 / sink），行 = 轮次；列间距与节点宽度见 sizeFor()。
const Y_GAP = 84;
const NODE_H = 64;
const MIN_X_GAP = 30; // 边标签最短两字，留出这点空隙才不会压到节点上

/**
 * fitView 是等比缩小：容器只有 ~490px 时，固定 200px 列距的四列布局会被压到 0.5 倍，
 * 节点里 13px 的字掉到 7px——图还在，但没人读得动。所以按容器宽度反推尺寸，
 * 把缩放钉在 0.9 左右：宁可排得挤一点，也不让字号糊掉。
 */
function sizeFor(width: number) {
  const target = width > 0 ? width / 0.9 : 900;
  const nodeW = target < 560 ? 112 : target < 700 ? 132 : 152;
  const xGap = Math.max(nodeW + MIN_X_GAP, Math.min(200, (target - nodeW) / 3));
  return { nodeW, xGap };
}

const EDGE_STYLE: Record<EdgeState, { stroke: string; dashed?: boolean }> = {
  payload: { stroke: "#ff8fa3", dashed: true },
  call: { stroke: "#4b5566" },
  blocked: { stroke: "#7ee2b8" },
  tainted: { stroke: "#ffd08a", dashed: true },
  captured: { stroke: "#ff8fa3" },
};

// 边的颜色已经说了「拦下 / 放行 / 送达」，标签只留这两个字；命中层级看悬停。
const SHORT_STATE: Record<EdgeState, string> = {
  payload: "",
  call: "",
  blocked: "拦下",
  tainted: "放行",
  captured: "送达",
};

// 节点底色改用语义色的低透明写法：bad=攻击面、warn=污点源、sky=Agent、slate=普通调用。
const NODE_STYLE: Record<string, { border: string; tint: string }> = {
  attacker: { border: "rgba(255,143,163,0.5)", tint: "rgba(255,143,163,0.12)" },
  agent: { border: "rgba(56,189,248,0.5)", tint: "rgba(14,165,233,0.12)" },
  call: { border: "rgba(148,163,184,0.35)", tint: "rgba(148,163,184,0.10)" },
  source: { border: "rgba(255,208,138,0.5)", tint: "rgba(255,208,138,0.14)" },
  sink: { border: "rgba(255,143,163,0.5)", tint: "rgba(255,143,163,0.12)" },
};

function truncated(text: string, n: number) {
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

/**
 * 污点传播图：分层布局（攻击者 → Agent → 工具调用 → sink）由后端 `graph.column` 给出，
 * 同一轮的源与 sink 靠 `graph.round` 对齐到同一行。
 *
 * 视觉语义刻意区分两类事实：绿色 = 代理拦下的污点边（防御生效），
 * 红色 = 载荷真的送达后端（防御关闭时唯一可得的一手证据）。
 */
export default function TaintGraphView({ graph, height = 460 }: { graph: TaintGraph; height?: number }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { nodes, edges, canvasHeight } = useMemo(() => layout(graph, height, width), [graph, height, width]);

  if (!nodes.length) return <div className="panel text-sm text-slate-400">这组运行没有可画的节点。</div>;

  const summary = graph.nodes
    .map((n) => `${n.label}（${n.kind}${n.round != null ? `，第 ${n.round} 轮` : ""}）`)
    .join("；");

  return (
    <>
      <div
        ref={box}
        role="img"
        aria-label="污点传播图：绿边=代理拦下，红线=载荷送达"
        className="overflow-hidden rounded-xl border border-line"
        style={{ height: canvasHeight }}
      >
        {width > 0 && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.04, minZoom: 0.86, maxZoom: 1 }}
            minZoom={0.2}
            nodesConnectable={false}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#202634" />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        )}
      </div>
      <p className="sr-only">污点传播图节点：{summary}。</p>
    </>
  );
}

/**
 * 分层由后端 `graph.column` 决定；这里只兜一种情况：产物里的调用全挤在源列
 * （ECS 上的 api 镜像还没重建时就是这种老形状）。被拦下/放行的污点边指向的那个调用
 * 本身就是 sink，按边拓扑挪到最后一列即可——布局是显示层的事，不该被后端版本卡住。
 */
function splitSinkColumn(graph: TaintGraph): TaintGraph {
  if (new Set(graph.nodes.map((n) => n.column)).size >= 4) return graph;
  const sinks = new Set(
    graph.edges.filter((e) => e.state === "blocked" || e.state === "tainted").map((e) => e.target),
  );
  if (!sinks.size) return graph;
  return {
    ...graph,
    nodes: graph.nodes.map((n: GraphNode) => (sinks.has(n.id) ? { ...n, column: 3, kind: "sink" as const } : n)),
  };
}

function layout(graph: TaintGraph, wantedHeight: number, width: number) {
  const { nodeW, xGap } = sizeFor(width);
  const laid = splitSinkColumn(graph);
  // 行号取「列内序号」，排序键用轮次：后端把源与 sink 分到两列后，两列各自 6 行正好对齐；
  // 而旧产物里 12 个调用同在一列时，也只是往下排，不会叠成同一个坐标。
  const perColumn = new Map<number, number>();
  const ordered = [...laid.nodes].sort(
    (a, b) => a.column - b.column || (a.round ?? -1) - (b.round ?? -1) || a.id.localeCompare(b.id),
  );

  const nodes: Node[] = ordered.map((n: GraphNode) => {
    const row = perColumn.get(n.column) ?? 0;
    perColumn.set(n.column, row + 1);
    const style = NODE_STYLE[n.kind] ?? NODE_STYLE.call;
    const [tool, args] = splitLabel(n.label);
    return {
      id: n.id,
      position: { x: n.column * xGap, y: row * Y_GAP },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        border: `1px solid ${style.border}`,
        background: style.tint,
        borderRadius: 10,
        boxShadow: "none",
        width: nodeW,
        height: NODE_H,
        padding: "5px 7px",
      },
      data: {
        label: (
          <div className="text-left leading-tight" title={n.label}>
            <span className="sr-only">{`${n.label}，${n.kind}${n.round != null ? `，第 ${n.round} 轮` : ""}`}</span>
            <div className="mono text-[8px] uppercase tracking-wider text-slate-500" aria-hidden="true">
              {n.kind}
              {n.round != null ? ` · r${n.round}` : ""}
            </div>
            <div className="truncate text-[14px] font-semibold text-slate-100" aria-hidden="true">
              {tool}
            </div>
            {args && (
              <div className="mono truncate text-[9px] text-slate-400" aria-hidden="true">
                {truncated(args, 16)}
              </div>
            )}
          </div>
        ),
      },
    };
  });

  const rows = Math.max(1, ...[...perColumn.values()]);
  // 高度跟着行数走（上限 1120 ≈ 12 行，是全矩阵里最深的一格）：容器压到 460 时
  // fitView 会把纵向也缩一遍，字号又掉回 7px。宁可让详情面板长一点。
  const canvasHeight = Math.max(wantedHeight, Math.min(rows * Y_GAP + NODE_H + 40, 1120));

  const edges: Edge[] = graph.edges.map((e: GraphEdge) => {
    const style = EDGE_STYLE[e.state] ?? EDGE_STYLE.call;
    const label = edgeLabel(e);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: label || undefined,
      animated: e.state === "captured",
      style: {
        stroke: style.stroke,
        strokeWidth: e.state === "blocked" ? 1.8 : 1.2,
        strokeDasharray: style.dashed ? "5 4" : undefined,
      },
      labelStyle: { fill: "#c8cede", fontSize: 12 },
      labelBgStyle: { fill: "#151922", fillOpacity: 0.95 },
      labelBgPadding: [3, 2],
      labelBgBorderRadius: 4,
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: style.stroke },
      title: [EDGE_LABEL[e.state] ?? e.state, e.label, e.hits > 1 ? `重复 ${e.hits} 次` : "", e.snippet ?? ""]
        .filter(Boolean)
        .join(" · "),
    };
  });

  return { nodes, edges, canvasHeight };
}

/** 后端给的标签是 `tool · args`，这里拆开好排版：工具名不缩，参数留一小截。 */
function splitLabel(label: string): [string, string] {
  const i = label.indexOf(" · ");
  return i < 0 ? [label, ""] : [label.slice(0, i), label.slice(i + 3)];
}

/** 窄列距下标签只能两三字：轮次已在节点头上，命中层级放进悬停，这里只留结论。 */
function edgeLabel(e: GraphEdge): string {
  const repeat = e.hits > 1 ? ` ×${e.hits}` : "";
  if (e.state === "call") return repeat.trim();
  return SHORT_STATE[e.state] ? `${SHORT_STATE[e.state]}${repeat}` : `${e.label}${repeat}`;
}
