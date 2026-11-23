import type {
  DemoBundle,
  Health,
  MetricsPayload,
  RunDetail,
  RunRequest,
  RunRow,
  TargetsResponse,
} from "./types";

/** 生产环境同域反代（Caddy）时留空即可；跨域部署才需要设 VITE_API_BASE。 */
const BASE = import.meta.env.VITE_API_BASE ?? "";
/** VITE_STATIC=1：无后端静态演示版，数据读自 public/data/（web/scripts/dump_static_data.py 生成）。 */
const STATIC = import.meta.env.VITE_STATIC === "1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

async function staticGet<T>(name: string): Promise<T> {
  const res = await fetch(`./data/${name}`);
  if (!res.ok) throw new Error(`static data ${name} → ${res.status}`);
  return (await res.json()) as T;
}

let _staticDetails: Promise<Record<string, RunDetail>> | null = null;

const staticApi = {
  health: () => staticGet<Health>("health.json"),
  targets: () => staticGet<TargetsResponse>("targets.json"),
  metrics: () => staticGet<MetricsPayload>("metrics.json"),
  runs: async (f: RunFilter = {}) => {
    const all = await staticGet<RunRow[]>("runs-index.json");
    const filtered = all.filter(
      (r) =>
        (!f.target || r.target === f.target) &&
        (!f.attack_class || r.attack_class === f.attack_class) &&
        (!f.defense || r.defense === f.defense),
    );
    const offset = f.offset ?? 0;
    const limit = f.limit ?? filtered.length;
    return {
      items: filtered.slice(offset, offset + limit),
      limit,
      offset,
      stats: (await staticGet<Health>("health.json")).history,
    };
  },
  run: async (runId: string) => {
    _staticDetails ??= staticGet<Record<string, RunDetail>>("runs-detail.json");
    const detail = (await _staticDetails)[runId];
    if (!detail) throw new Error(`静态数据缺少运行 ${runId}`);
    return detail;
  },
  demoPreset: () => staticGet<DemoBundle>("demo.json"),
  startRun: () => Promise.reject(new Error(STATIC_HINT)),
  startDemo: () => Promise.reject(new Error(STATIC_HINT)),
  startMatrix: () => Promise.reject(new Error(STATIC_HINT)),
};

const STATIC_HINT =
  "静态演示版：实时运行需本地部署（python -m platform_api serve）。本页数据来自 120 组实跑产物，可在运行台逐组查看证据。";

export interface RunFilter {
  target?: string;
  attack_class?: string;
  defense?: string;
  limit?: number;
  offset?: number;
}

const liveApi = {
  health: () => get<Health>("/health"),
  targets: () => get<TargetsResponse>("/targets"),
  metrics: (refresh = false) => get<MetricsPayload>(`/metrics${refresh ? "?refresh=true" : ""}`),
  runs: (f: RunFilter = {}) => {
    const q = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => v !== undefined && v !== "" && q.set(k, String(v)));
    return get<{ items: RunRow[]; limit: number; offset: number; stats: Health["history"] }>(
      `/runs?${q.toString()}`,
    );
  },
  run: (runId: string) => get<RunDetail>(`/runs/${encodeURIComponent(runId)}`),
  demoPreset: () => get<DemoBundle>("/demo/preset"),
  startRun: (body: RunRequest) => post<{ run_id: string; status: string }>("/runs", body),
  startDemo: (body: RunRequest) =>
    post<{ status: string; runs: Array<{ run_id: string; defense: string }> }>("/demo", body),
  startMatrix: (body: Record<string, unknown>) =>
    post<{ status: string; cells: number }>("/matrix", body),
};

export const api = STATIC ? staticApi : liveApi;

export const exportUrl = (runId: string, format: "json" | "md" | "html") =>
  STATIC
    ? `./data/exports/${encodeURIComponent(runId)}.${format}`
    : `${BASE}/api/runs/${encodeURIComponent(runId)}/export?format=${format}`;
