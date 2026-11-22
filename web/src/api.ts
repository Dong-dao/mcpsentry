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

export interface RunFilter {
  target?: string;
  attack_class?: string;
  defense?: string;
  limit?: number;
  offset?: number;
}

export const api = {
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

export const exportUrl = (runId: string, format: "json" | "md" | "html") =>
  `${BASE}/api/runs/${encodeURIComponent(runId)}/export?format=${format}`;
