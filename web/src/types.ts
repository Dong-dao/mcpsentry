/** 与 platform_api 的响应一一对应；判定语义一律沿用 engine/contracts.py，前端不重新发明。 */

export type VerdictType =
  | "exfiltration"
  | "forbidden_call"
  | "poisoning_executed"
  | "rug_pull_triggered"
  | "attack_failed"
  | "n_a_negative_control";

export type EdgeState = "payload" | "call" | "blocked" | "tainted" | "captured";
export type NodeKind = "attacker" | "agent" | "call" | "source" | "sink";
export type Tier = "off" | "block" | "alert";

/** 自定义 MCP 接入配置：与 platform_api/custom.py 的 CustomRunBody 一一对应。 */
export interface CustomConfig {
  name: string;
  command: string[];
  tool_classes: Record<string, "source" | "sink" | "neutral">;
  sinks: string[];
  carrier_tool?: string;
  attack_class?: string;
  seed?: number;
  defense?: Tier;
  hardened?: boolean;
  description?: string;
  note?: string;
  confirm?: boolean;
}

export const VERDICT_LABEL: Record<VerdictType, string> = {
  exfiltration: "数据外渗成功",
  forbidden_call: "越权调用成功",
  poisoning_executed: "投毒描述被执行",
  rug_pull_triggered: "描述漂移已触发",
  attack_failed: "攻击失败",
  n_a_negative_control: "负对照（未执行）",
};

export const ATTACK_LABEL: Record<string, string> = {
  A1_direct_injection: "A1 直接注入",
  A2_indirect_tool_result: "A2 工具返回间接注入",
  A3_description_poisoning: "A3 工具描述投毒",
  A4_exfiltration_inducement: "A4 外渗诱导",
};

export const EDGE_LABEL: Record<EdgeState, string> = {
  payload: "注入进入上下文",
  call: "常规调用",
  blocked: "污点命中 · 已拦截",
  tainted: "污点标记 · 放行（告警）",
  captured: "载荷送达后端",
};

export interface Evidence {
  kind: string;
  call_id: string;
  tool: string;
  field: string;
  snippet: string;
  extra: Record<string, unknown>;
}

export interface Verdict {
  success: boolean;
  type: VerdictType;
  evidence: string;
  evidence_details: Evidence[];
}

export interface ToolCall {
  call_id: string;
  tool: string;
  args: Record<string, unknown>;
  result_snippet: string;
  timestamp_ms: number;
}

export interface TrajectoryStep {
  round: number;
  payload: string;
  target_response: string;
  tool_calls: ToolCall[];
}

export interface TaintEdge {
  source_call_id: string;
  source_tool: string;
  sink_call_id: string;
  sink_tool: string;
  sink_field: string;
  layer: string;
  blocked: boolean;
  matched_snippet: string;
}

export interface SinkCapture {
  run_id: string;
  call_id: string;
  ts: number;
  tool: string;
  payload: Record<string, unknown>;
}

export interface FlowEntry {
  ts?: number;
  method?: string;
  tool?: string;
  [key: string]: unknown;
}

export interface Report {
  schema_version: string;
  run_id: string;
  verdict: Verdict;
  trajectory: TrajectoryStep[];
  taint_edges: TaintEdge[];
  metrics: {
    latency_overhead_ms: Record<string, number>;
    substring_hits: number;
    semantic_layer_calls: number;
    downgraded: boolean;
  };
  repro: { seed: number; engine_version: string; payload_hash: string };
}

export interface RunConfig {
  schema_version: string;
  run_id: string;
  target: { id: string; name: string; agent_endpoint: string; mcp_servers: string[] };
  attack: {
    class_?: string;
    class?: string;
    seed: number;
    max_rounds: number;
    carrier: string;
    objective_marker: string;
  };
  defense: { proxy: boolean; policy: string; downgrade_on_untrusted: boolean };
  oracle: { canary: string; forbidden_sinks: string[]; attacker_markers: string[] };
  engine_version: string;
}

export interface RunMeta {
  run_id: string;
  target: string;
  attack_class: string;
  seed: number;
  defense: string;
  policy?: string;
  verdict_type: VerdictType;
  success: boolean;
  rounds_used: number;
  rounds_limit: number;
  success_round?: number;
  replay_hash: string;
  taint_edge_count: number;
  sink_capture_count: number;
  flow_entry_count: number;
  semantic_layer: boolean;
  paraphrase: boolean;
  skipped?: string;
  wall_ms?: number;
  variants_tried?: string[];
  evidence?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  column: number;
  round?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  state: EdgeState;
  hits: number;
  snippet?: string;
  sink_field?: string;
}

export interface TaintGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RunDetail {
  run_id: string;
  subdir: string;
  path: string;
  config: RunConfig;
  report: Report;
  meta: RunMeta;
  latency: Record<string, number>;
  trajectory: TrajectoryStep[];
  flow: FlowEntry[];
  sink_capture: SinkCapture[];
  graph: TaintGraph;
  verdict: Verdict;
  remediation: string[];
  history?: RunRow | null;
}

export interface RunRow {
  run_id: string;
  target: string;
  attack_class: string;
  seed: number;
  defense: Tier | string;
  policy: string | null;
  verdict: VerdictType | null;
  success: number | null;
  rounds_used: number | null;
  replay_hash: string | null;
  source: string;
  status: "queued" | "running" | "done" | "error" | string;
  error: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface HistoryStats {
  runs: number;
  successes: number;
  by_verdict: Record<string, number>;
}

export interface Health {
  ok: boolean;
  results_root: string;
  runs_present: boolean;
  metrics_bundled: boolean;
  demo_bundled: boolean;
  history: HistoryStats;
}

export interface TargetRow {
  id: string;
  name: string;
  profile: string;
  port: number;
  vulnerability: string;
  description: string;
  sinks: string[];
  mcp_servers: string[];
  hardened: boolean;
  applicable: string[];
  na: string[];
}

export interface TargetsResponse {
  targets: TargetRow[];
  attack_classes: string[];
  seeds: number[];
  matrix: { total: number; applicable: number; negative_control: number };
}

export interface AsrRow {
  target: string;
  attack_class: string;
  defense: string;
  runs: number;
  success: number;
  asr: number;
  asr_first_round: number;
}

export interface MetricsPayload {
  engine_version: string;
  canonical: {
    asr: Record<string, number[]>;
    defense_effectiveness: Record<string, number>;
    detection_rate: [number, number];
    fpr: [number, number];
    replay_consistency: [number, number];
    negative_control_violations: string[];
  };
  asr_view: AsrRow[];
  effectiveness_applicable_only: Record<
    string,
    { off: { runs: number; success: number; asr: number }; on: { runs: number; success: number; asr: number }; delta: number }
  >;
  asr_by_target: { off: Record<string, { runs: number; success: number; asr: number }>; block: Record<string, { runs: number; success: number; asr: number }> };
  negative_control: { cells: number; success: number; expected: number };
  deviations: Array<Record<string, unknown>>;
  latency_overhead: {
    pairs: number;
    p50_delta_ms: number | null;
    p95_delta_ms: number | null;
    max_p95_delta_ms?: number;
    rows: Array<{
      target: string;
      attack_class: string;
      seed: number;
      p50_off_ms: number;
      p50_on_ms: number;
      p50_delta_ms: number;
      p95_off_ms: number;
      p95_on_ms: number;
      p95_delta_ms: number;
    }>;
  };
  normal_suite: {
    total: number;
    blocked: number;
    intended_pressure: number;
    unintended_blocked: number;
    fpr_all: number;
    fpr_excluding_design: number;
    rows: Array<Record<string, unknown>>;
  };
  counts: { runs: number; executed: number; negative_control: number };
}

export interface DemoRun extends RunDetail {
  defense: Tier;
  narrative: string;
  markdown: string;
}

export interface DemoBundle {
  kind: string;
  title: string;
  engine_version: string;
  generated_at: string;
  cell: { target: string; attack_class: string; seed: number };
  narrative: Record<string, string>;
  runs: DemoRun[];
  compliance: string;
}

export interface RunRequest {
  target: string;
  attack_class: string;
  seed: number;
  defense: Tier;
  paraphrase?: boolean;
  semantic?: boolean;
  note?: string;
}
