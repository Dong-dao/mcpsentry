"""报告服务：把 `bench/results/**` 的原始产物读成前端能直接画的视图模型。

这一层不算任何安全数字——判定、ASR、FPR 全部来自 engine 与 bench/report.py。
它只做三件事：读文件、把污点边摊成图、给导出准备好可读文本。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import export

JSONL_FILES = ("trajectory.jsonl", "flow.jsonl", "sink_capture.jsonl")
JSON_FILES = ("config.json", "report.json", "meta.json", "latency.json")
# 查找顺序即优先级：矩阵正式产物 > 平台临时运行 > 正常任务 > 重放
SUBDIRS = ("runs", "platform", "normal", "replays")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_run(results_root: Path, run_id: str) -> tuple[Path, str] | None:
    """在约定的几个子目录里找一组运行；重放目录取最新一次 attempt。"""
    results_root = Path(results_root)
    for subdir in SUBDIRS:
        base = results_root / subdir / run_id
        if (base / "report.json").exists():
            return base, subdir
        if base.is_dir():
            attempts = sorted((d for d in base.iterdir() if (d / "report.json").exists()))
            if attempts:
                return attempts[-1], subdir
    return None


def taint_graph(
    report: dict[str, Any],
    config: dict[str, Any],
    *,
    sink_capture: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """污点传播图：攻击者 → 靶标 Agent → 工具，以及 source→sink 的污点边。

    `column` 是给前端的分层布局提示（0 最左）；节点 id 用 call_id，
    同一工具多次调用因此是两个节点——图要讲的是"这一次调用污染了那一次外发"。

    防御关闭时代理不在链路上，`report.taint_edges` 与轨迹里的 call_id 都是空的，图会退化
    成两个点。这时用 `sink_capture.jsonl`（靶场后端原样落盘的 sink 载荷）补出送达节点：
    它是真实产物而非代理的推断，所以状态标 `captured`，不进任何检出计数。
    """
    target_id = (config.get("target") or {}).get("id", "TARGET")
    nodes: dict[str, dict[str, Any]] = {
        "attacker": {"id": "attacker", "label": "攻击者 payload", "kind": "attacker", "column": 0},
        f"agent:{target_id}": {
            "id": f"agent:{target_id}",
            "label": f"{target_id} {(config.get('target') or {}).get('name', '')}".strip(),
            "kind": "agent",
            "column": 1,
        },
    }
    edges: dict[str, dict[str, Any]] = {}

    def add_edge(source: str, target: str, *, label: str, state: str, **extra: Any) -> None:
        """按 (source, target) 去重：自适应攻击会逐轮重复同一批调用，重复只累加 hits。

        前端用边 id 做 key，重复 id 会直接报 key 冲突并把同一根线画五遍。
        """
        eid = f"{source}->{target}"
        edge = edges.setdefault(
            eid, {"id": eid, "source": source, "target": target, "state": state, "label": label, "hits": 0}
        )
        edge["hits"] += 1
        edge.update({k: v for k, v in extra.items() if v})

    add_edge(
        "attacker",
        f"agent:{target_id}",
        label=f"{len(report.get('trajectory', []))} 轮",
        state="payload",
    )

    for step in report.get("trajectory", []):
        for call in step.get("tool_calls", []):
            cid = call.get("call_id") or f"{call.get('tool')}-{step['round']}"
            nodes.setdefault(
                cid,
                {
                    "id": cid,
                    "label": f"{call.get('tool')} · {json.dumps(call.get('args', {}), ensure_ascii=False)[:60]}",
                    "kind": "call",
                    "column": 2,
                    "round": step.get("round"),
                },
            )
            add_edge(f"agent:{target_id}", cid, label=f"round {step.get('round')}", state="call")

    for edge in report.get("taint_edges", []):
        src, dst = edge.get("source_call_id"), edge.get("sink_call_id")
        for key, label, kind, col in (
            (src, edge.get("source_tool"), "source", 2),
            (dst, edge.get("sink_tool"), "sink", 3),
        ):
            if key and key not in nodes:
                nodes[key] = {"id": key, "label": f"{label or key}", "kind": kind, "column": col}
        add_edge(
            src,
            dst,
            label=f"{edge.get('layer', '')}{'/blocked' if edge.get('blocked') else ''}",
            state="blocked" if edge.get("blocked") else "tainted",
            snippet=edge.get("matched_snippet", "")[:160],
            sink_field=edge.get("sink_field", ""),
        )

    # 只在代理完全没留下观测（防御关闭）时补节点，避免和 call_id 指向同一次调用画两遍。
    if sink_capture and not any(n["kind"] in ("call", "sink") for n in nodes.values()):
        for i, cap in enumerate(sink_capture):
            tool = cap.get("tool", "sink")
            cid = f"cap-{i:02d}-{tool}"
            args = json.dumps(cap.get("payload") or {}, ensure_ascii=False)
            nodes[cid] = {"id": cid, "label": f"{tool} · {args[:60]}", "kind": "sink", "column": 3}
            add_edge(
                f"agent:{target_id}",
                cid,
                label="载荷送达后端",
                state="captured",
                snippet=args[:160],
            )

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def load_run(results_root: Path, run_id: str) -> dict[str, Any] | None:
    found = find_run(results_root, run_id)
    if not found:
        return None
    base, subdir = found
    report = _read_json(base / "report.json")
    config = _read_json(base / "config.json")
    meta = _read_json(base / "meta.json")
    latency = _read_json(base / "latency.json")
    trajectory = _read_jsonl(base / "trajectory.jsonl")
    flow = _read_jsonl(base / "flow.jsonl")
    sink_capture = _read_jsonl(base / "sink_capture.jsonl")
    detail = {
        "run_id": run_id,
        "subdir": subdir,
        "path": str(base.relative_to(results_root.parent)),
        "config": config,
        "report": report,
        "meta": meta,
        "latency": latency,
        "trajectory": trajectory,
        "flow": flow,
        "sink_capture": sink_capture,
        "graph": taint_graph(report, config, sink_capture=sink_capture),
        "verdict": report.get("verdict", {}),
    }
    # 修复建议只算一次：导出与前端读同一个字段，避免两处口径漂移
    detail["remediation"] = export.remediation_lines(detail)
    return detail
