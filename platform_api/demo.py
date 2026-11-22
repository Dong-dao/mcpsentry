"""一键 demo 的预置包：把"评委点开就有东西看"变成静态资产。

为什么要预置：ECS 只有 2 核 4G，现场并发跑攻击会排队；而作品帖评审的第一屏
必须立刻看到一份真报告。bundle 由真实运行生成（`python -m platform_api build-demo`），
不是手填的样例数据——数字与 `bench/results` 里的产物同源。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.matrix import Cell
from bench.runner import run_cell
from engine import ENGINE_VERSION
from range.specs import target

from . import export, reports
from .orchestr import RESULTS_ROOT

DEMO_DIR = Path(__file__).resolve().parent / "demo"
BUNDLE = DEMO_DIR / "t1-a2-pair.json"

DEMO_CELL = dict(target="T1", attack_class="A2_indirect_tool_result", seed=42)

NARRATIVE = {
    "off": "防御关闭：注入内容随工具返回进入 Agent 上下文，客户文档（含金丝雀）被"
    "原样交给 send_email —— 判定 exfiltration，证据是金丝雀出现在 sink 载荷里。",
    "block": "污点代理开启：read_doc 的返回被打上污点标记，进 sink 前命中子串层，"
    "调用被拒 —— 判定 attack_failed，污点边保留为拦截证据。",
    "reading": "两档跑的是同一个 RunConfig、同一个 seed，唯一差别是代理。"
    "把两栏并排放，就是这套防御在这个靶标上的净效果。",
}


async def build_bundle(*, out: Path = BUNDLE) -> Path:
    """真跑一对 off/block，再把详情裁成前端直接可用的 bundle。"""
    entry = target(DEMO_CELL["target"])
    runs: list[dict[str, Any]] = []
    for tier in ("off", "block"):
        cell = Cell(entry=entry, attack_class=DEMO_CELL["attack_class"], seed=DEMO_CELL["seed"], defense=tier)
        run_id = f"demo-{entry.id}-{cell.short_class}-s{cell.seed}-{tier}"
        outcome = await run_cell(cell, RESULTS_ROOT, subdir="platform", run_id=run_id)
        detail = reports.load_run(RESULTS_ROOT, outcome.run_id)
        if detail is None:  # pragma: no cover - run_cell 刚落盘，理论上必有
            raise RuntimeError(f"run {outcome.run_id} 未产出 report.json")
        runs.append(
            {
                "run_id": detail["run_id"],
                "defense": tier,
                "verdict": detail["verdict"],
                "config": detail["config"],
                "report": detail["report"],
                "graph": detail["graph"],
                "trajectory": detail["trajectory"],
                "flow": detail["flow"],
                "sink_capture": detail["sink_capture"],
                "meta": detail["meta"],
                "markdown": export.to_markdown(detail),
                "narrative": NARRATIVE[tier],
            }
        )

    bundle = {
        "kind": "mcpsentry.demo",
        "title": f"{entry.name} × {DEMO_CELL['attack_class']}",
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cell": DEMO_CELL,
        "narrative": NARRATIVE,
        "runs": runs,
        "compliance": export.COMPLIANCE,
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return out


__all__ = ["build_bundle", "BUNDLE", "DEMO_CELL", "NARRATIVE"]
