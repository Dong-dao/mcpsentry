"""把 bench/results 产物 dump 成前端静态演示数据（方案 A：无后端 Qoder Sites 部署）。

用 TestClient 直接跑 platform_api 应用，逐接口拉取并把响应落盘到 web/public/data/，
形状与线上 API 完全一致；导出三格式也一并生成。运行方式：

    python web/scripts/dump_static_data.py

产物（web/public/data/）：
    health.json targets.json metrics.json demo.json runs-index.json runs-detail.json
    exports/<run_id>.{md,html,json}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import platform_api.app as api  # noqa: E402

OUT = ROOT / "web" / "public" / "data"
EXPORTS = OUT / "exports"


def _write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {path.relative_to(ROOT)} ({path.stat().st_size} B)")


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    with TestClient(api.app) as client:
        print("dumping endpoints…")
        health = client.get("/api/health").json()
        # 打包给公网的证据包里不带本机绝对路径
        health["results_root"] = "/app/bench/results"
        _write("health.json", health)
        _write("targets.json", client.get("/api/targets").json())
        _write("metrics.json", client.get("/api/metrics").json())
        _write("demo.json", client.get("/api/demo/preset").json())

        items: list[dict] = []
        while True:
            page = client.get("/api/runs", params={"limit": 500, "offset": len(items)}).json()["items"]
            if not page:
                break
            items.extend(page)
        _write("runs-index.json", items)
        details: dict[str, dict] = {}
        exports_n = 0
        for item in items:
            run_id = item["run_id"]
            detail = client.get(f"/api/runs/{run_id}").json()
            details[run_id] = detail
            for fmt in ("md", "html", "json"):
                res = client.get(f"/api/runs/{run_id}/export", params={"format": fmt})
                (EXPORTS / f"{run_id}.{fmt}").write_text(res.text, encoding="utf-8")
                exports_n += 1
        _write("runs-detail.json", details)
        print(f"exports: {exports_n} files")

    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"total data size: {total / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
