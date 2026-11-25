import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { NavLink } from "./components/ui";
import { useRoute } from "./router";
import Custom from "./pages/Custom";
import Dashboard from "./pages/Dashboard";
import Demo from "./pages/Demo";
import Landing from "./pages/Landing";
import MetricsPage from "./pages/MetricsPage";
import type { Health } from "./types";

const NAV = [
  { path: "/", label: "概览" },
  { path: "/demo", label: "一键 demo" },
  { path: "/dashboard", label: "运行台" },
  { path: "/custom", label: "接入自己的 MCP" },
  { path: "/metrics", label: "指标" },
];

const STATIC = import.meta.env.VITE_STATIC === "1";

export default function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthChecked, setHealthChecked] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    setHealthChecked(false);
    api.health()
      .then((h) => {
        if (cancelled) return;
        setHealth(h);
        setHealthChecked(true);
      })
      .catch(() => {
        if (cancelled) return;
        setHealth(null);
        setHealthChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, [route.path]);

  // 路由变化后收起移动菜单；展开时焦点进首项，Esc 回到汉堡按钮。
  useEffect(() => {
    setMenuOpen(false);
  }, [route.path]);

  useEffect(() => {
    if (!menuOpen) return;
    menuRef.current?.querySelector("a")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const page = NAV.find((n) => n.path === route.path) ?? NAV[0];

  let healthTone = "v-info";
  let healthText = "检测中…";
  let healthLabel = "正在检测后端服务状态";
  if (healthChecked && health) {
    healthTone = STATIC ? "v-info" : "v-good";
    healthText = `${STATIC ? "静态演示版" : "后端在线"} · ${health.history.runs} 组`;
    healthLabel = `${STATIC ? "静态演示版" : "后端在线"}，已索引 ${health.history.runs} 组运行`;
  } else if (healthChecked) {
    healthTone = "v-bad";
    healthText = "后端离线";
    healthLabel = "后端离线，无法读取 /api/health";
  }
  const healthBadge = (
    <span
      className={`badge ${healthTone}`}
      role="status"
      aria-live="polite"
      aria-label={healthLabel}
      tabIndex={-1}
    >
      {healthText}
    </span>
  );

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-ink/85 backdrop-blur">
        <div className="mx-auto max-w-7xl px-6 py-4">
          <div className="flex items-center gap-3">
            <a href="#/" className="flex items-center gap-2" onClick={() => setMenuOpen(false)}>
              <span className="grid h-7 w-7 place-items-center rounded-md bg-sky-500/20 text-base font-bold text-sky-300">
                M
              </span>
              <span className="text-base font-semibold tracking-wide text-slate-100">MCPSentry</span>
              <span className="mono hidden text-xs text-slate-500 sm:inline">MCP 工具链污点评测平台</span>
            </a>
            <nav aria-label="主导航" className="ml-auto hidden items-center gap-1 md:flex">
              {NAV.map((n) => (
                <NavLink key={n.path} path={n.path} active={n.path === page.path} aria-current={n.path === page.path ? "page" : undefined}>
                  {n.label}
                </NavLink>
              ))}
            </nav>
            <div className="ml-auto hidden md:block">{healthBadge}</div>
            <button
              ref={menuButtonRef}
              type="button"
              className="btn ml-auto min-h-11 px-3 md:hidden"
              aria-expanded={menuOpen}
              aria-controls="main-nav"
              aria-label={menuOpen ? "关闭导航菜单" : "打开导航菜单"}
              onClick={() => setMenuOpen((v) => !v)}
            >
              <span aria-hidden="true">{menuOpen ? "✕" : "☰"}</span>
              <span>菜单</span>
            </button>
          </div>
          {menuOpen && (
            <nav
              ref={menuRef}
              id="main-nav"
              aria-label="主导航"
              className="mt-3 flex flex-col gap-1 border-t border-line pt-3 md:hidden"
            >
              {NAV.map((n) => (
                <NavLink
                  key={n.path}
                  path={n.path}
                  active={n.path === page.path}
                  aria-current={n.path === page.path ? "page" : undefined}
                  onNavigate={() => setMenuOpen(false)}
                >
                  {n.label}
                </NavLink>
              ))}
              <div className="mt-2 px-1">{healthBadge}</div>
            </nav>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {page.path === "/" && <Landing />}
        {page.path === "/demo" && <Demo />}
        {page.path === "/dashboard" && <Dashboard />}
        {page.path === "/custom" && <Custom />}
        {page.path === "/metrics" && <MetricsPage />}
      </main>

      <footer className="border-t border-line px-6 py-8 text-sm leading-6 text-slate-500">
        <div className="mx-auto max-w-7xl">
          <p>
            MCPSentry · 靶场 T1–T5 + 污点代理 + 自适应攻击引擎。内置靶场的 sink 全部是 mock
            （只落盘、不发真信、不出网）；自定义接入只打上传者自己授权的 MCP 工具链。
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
