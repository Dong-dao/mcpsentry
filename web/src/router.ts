import { useEffect, useState } from "react";

export interface Route {
  path: string;
  query: URLSearchParams;
}

/**
 * hash 路由：Qoder Sites 是静态托管，深链 `/#/dashboard?run=x` 不需要服务端 rewrite，
 * 也不用为此多引一个 router。
 */
function parse(): Route {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, qs = ""] = raw.split("?");
  return { path: path || "/", query: new URLSearchParams(qs) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function href(path: string, query?: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const suffix = q.toString();
  return `#${path}${suffix ? `?${suffix}` : ""}`;
}

export function navigate(path: string, query?: Record<string, string | undefined>): void {
  window.location.hash = href(path, query);
}
