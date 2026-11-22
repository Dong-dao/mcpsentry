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
import { useMemo } from "react";
import type { EdgeState, GraphEdge, GraphNode, TaintGraph } from "../types";
import { EDGE_LABEL } from "../types";

const X_GAP = 300;
const Y_GAP = 104;

const EDGE_STYLE: Record<EdgeState, { stroke: string; dashed?: boolean }> = {
  payload: { stroke: "#ff8fa3", dashed: true },
  call: { stroke: "#4b5566" },
  blocked: { stroke: "#7ee2b8" },
  tainted: { stroke: "#ffd08a", dashed: true },
  captured: { stroke: "#ff8fa3" },
};

const NODE_STYLE: Record<string, { border: string; tint: string }> = {
  attacker: { border: "#7a2733", tint: "#2a1116" },
  agent: { border: "#2b4a86", tint: "#131c2b" },
  call: { border: "#2c3444", tint: "#161b25" },
  source: { border: "#7a5a1f", tint: "#241d10" },
  sink: { border: "#7a2733", tint: "#2a1116" },
};

function truncated(text: string, n: number) {
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

/**
 * 污点传播图：分层布局（攻击者 → Agent → 工具调用 → sink）由后端 `graph.column` 给出。
 *
 * 视觉语义刻意区分两类事实：绿色 = 代理拦下的污点边（防御生效），
 * 红色 = 载荷真的送达后端（防御关闭时唯一可得的一手证据）。
 */
export default function TaintGraphView({ graph, height = 460 }: { graph: TaintGraph; height?: number }) {
  const { nodes, edges } = useMemo(() => layout(graph), [graph]);

  if (!nodes.length) return <div className="panel text-sm text-slate-400">这组运行没有可画的节点。</div>;

  return (
    <div className="overflow-hidden rounded-xl border border-line" style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        minZoom={0.25}
        nodesConnectable={false}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#202634" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function layout(graph: TaintGraph): { nodes: Node[]; edges: Edge[] } {
  const perColumn = new Map<number, number>();
  const nodes: Node[] = graph.nodes.map((n: GraphNode) => {
    const row = perColumn.get(n.column) ?? 0;
    perColumn.set(n.column, row + 1);
    const style = NODE_STYLE[n.kind] ?? NODE_STYLE.call;
    return {
      id: n.id,
      position: { x: n.column * X_GAP, y: row * Y_GAP },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: { border: `1px solid ${style.border}`, background: style.tint, borderRadius: 10, width: 226 },
      data: {
        label: (
          <div className="text-left">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">
              {n.kind}
              {n.round ? ` · round ${n.round}` : ""}
            </div>
            <div className="mono mt-0.5 break-all text-slate-200">{truncated(n.label, 72)}</div>
          </div>
        ),
      },
    };
  });

  const edges: Edge[] = graph.edges.map((e: GraphEdge) => {
    const style = EDGE_STYLE[e.state] ?? EDGE_STYLE.call;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: `${truncated(e.label, 26)}${e.hits > 1 ? ` ×${e.hits}` : ""}`,
      animated: e.state === "captured",
      style: { stroke: style.stroke, strokeWidth: e.state === "blocked" ? 2 : 1.4, strokeDasharray: style.dashed ? "5 4" : undefined },
      labelStyle: { fill: "#c8cede", fontSize: 10 },
      labelBgStyle: { fill: "#151922", fillOpacity: 0.92 },
      markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
      title: EDGE_LABEL[e.state] ?? e.state,
    };
  });

  return { nodes, edges };
}
