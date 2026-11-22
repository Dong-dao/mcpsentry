import { useEffect, useState } from "react";
import { api } from "./api";
import { NavLink } from "./components/ui";
import { useRoute } from "./router";
import Dashboard from "./pages/Dashboard";
import Demo from "./pages/Demo";
import Landing from "./pages/Landing";
import MetricsPage from "./pages/MetricsPage";
import type { Health } from "./types";

const NAV = [
  { path: "/", label: "概览" },
  { path: "/demo", label: "一键 demo" },
  { path: "/dashboard", label: "运行台" },
  { path: "/metrics", label: "指标" },
];

export default function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [route.path]);

  const page = NAV.find((n) => n.path === route.path) ?? NAV[0];

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-ink/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-5 py-3">
          <a href="#/" className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-sky-500/20 text-sm font-bold text-sky-300">
              M
            </span>
            <span className="text-sm font-semibold tracking-wide text-slate-100">MCPSentry</span>
            <span className="mono hidden text-[11px] text-slate-500 sm:inline">MCP 工具链污点评测平台</span>
          </a>
          <nav className="ml-auto flex items-center gap-1">
            {NAV.map((n) => (
              <NavLink key={n.path} path={n.path} active={n.path === page.path}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <span
            className={`badge ${health ? "v-good" : "v-bad"}`}
            title={health ? `${health.history.runs} 组已索引` : "读不到 /api/health：后端未启动"}
          >
            {health ? `后端在线 · ${health.history.runs} 组` : "后端离线"}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-8">
        {page.path === "/" && <Landing />}
        {page.path === "/demo" && <Demo />}
        {page.path === "/dashboard" && <Dashboard />}
        {page.path === "/metrics" && <MetricsPage />}
      </main>

      <footer className="border-t border-line px-5 py-8 text-xs leading-6 text-slate-500">
        <div className="mx-auto max-w-7xl">
          <p>
            MCPSentry · 靶场 T1–T5 + 污点代理 + 自适应攻击引擎。所有攻击只打在自建靶场上，sink 全部是
            mock（只落盘、不发真信、不出网）。
          </p>
          <p className="mono mt-2">
            产物目录 bench/results · 指标 bench/metrics/summary.json · 接口文档{" "}
            <a className="text-slate-400 underline decoration-line hover:text-slate-200" href="/docs">
              /docs
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
