"""单组运行与批量执行：把 RunConfig 跑成 A 的 analysis 能直接读的产物目录。

产物布局（engine/analysis.py 模块文档里的约定，逐字对齐）：
    results/runs/<run_id>/{config.json, report.json, flow.jsonl, sink_capture.jsonl,
                           trajectory.jsonl, meta.json, latency.json}
    results/normal/<task_id>/{config.json, report.json, flow.jsonl, task.json}
    results/replays/<run_id>/<attempt>/{config.json, report.json, flow.jsonl}

meta.json / latency.json / trajectory.jsonl 是 B 的旁路材料，A 的复算不依赖它们。
延迟数字刻意不进 report.json：replay_hash 覆盖整个 report，运行时刻的耗时会
让"回放一致率 100%"必然失败。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine import ENGINE_VERSION
from engine.attacks import AttackEngine, AttackGenerator
from engine.contracts import (
    AttackClass,
    AttackSpec,
    DefenseSpec,
    Metrics,
    OracleSpec,
    Report,
    ReproInfo,
    RunConfig,
    TargetSpec,
    ToolCallRecord,
    TrajectoryStep,
)
from engine.oracle import Oracle, n_a_verdict
from engine.report import assemble_report, replay_hash

from range import workspace as ws
from range.evidence import FileEvidence
from range.planter import CarrierPlanter
from range.session import ProxyOptions, victim_params
from range.specs import DEFAULT_OBJECTIVE_MARKER, oracle_for
from range.specs import target as range_target
from range.victim import RangeVictim

RUNS_DIR = "runs"
NORMAL_DIR = "normal"
REPLAY_DIR = "replays"


@dataclass
class Outcome:
    run_id: str
    config: RunConfig
    report: Report
    meta: dict[str, Any] = field(default_factory=dict)
    latency: dict[str, Any] = field(default_factory=dict)
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.report.verdict.success


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return round(ordered[idx], 3)


def _latency_summary(timings: list[float], defense: bool) -> dict[str, Any]:
    return {
        "defense": "on" if defense else "off",
        "samples": len(timings),
        "p50_ms": percentile(timings, 0.50),
        "p95_ms": percentile(timings, 0.95),
        "mean_ms": round(statistics.fmean(timings), 3) if timings else 0.0,
        "total_ms": round(sum(timings), 3),
    }


def prepare_workdir(root: Path | str, config: RunConfig) -> Path:
    """每组一个独立工作区，跑前清干净，避免上一组的 sink/flow 证据串味。"""
    workdir = Path(root)
    store = ws.Workspace(workdir)
    store.root.mkdir(parents=True, exist_ok=True)
    FileEvidence(workdir).reset()
    store.capture.unlink(missing_ok=True)
    CarrierPlanter(config, workdir).reset()
    ws.prepare(workdir, canary=config.oracle.canary, run_id=config.run_id)
    return workdir


async def execute(
    config: RunConfig,
    workdir: Path,
    *,
    paraphrase: bool = False,
    semantic: bool = False,
) -> Outcome:
    """跑一组攻击：攻击引擎 → 靶标受害者 → （代理）→ oracle → Report。"""
    entry = range_target(config.target.id)
    options = ProxyOptions(
        policy=config.defense.policy.value,
        downgrade_on_untrusted=config.defense.downgrade_on_untrusted,
        seed=config.attack.seed,
        semantic=semantic,
    )
    params = victim_params(
        entry, workdir, defense=config.defense.proxy, options=options
    )
    evidence = FileEvidence(workdir)

    async with RangeVictim(params, entry, paraphrase=paraphrase) as victim:
        engine = AttackEngine(
            config=config,
            engine_version=ENGINE_VERSION,
            generator=AttackGenerator(config.attack),
            oracle=Oracle(config.oracle),
            agent=victim,
            planter=CarrierPlanter(config, workdir),
            evidence=evidence,
        )
        started = time.perf_counter()
        report, payloads = await engine.run()
        wall_ms = round((time.perf_counter() - started) * 1000, 3)

    captures, entries = evidence.snapshot()
    success_round = (
        report.trajectory[-1].round if report.verdict.success and report.trajectory else None
    )
    meta = {
        "run_id": config.run_id,
        "target": config.target.id,
        "attack_class": config.attack.class_.value,
        "seed": config.attack.seed,
        "defense": "on" if config.defense.proxy else "off",
        "policy": config.defense.policy.value,
        "downgrade_on_untrusted": config.defense.downgrade_on_untrusted,
        "paraphrase": paraphrase,
        "semantic_layer": semantic,
        "rounds_used": len(report.trajectory),
        "rounds_limit": config.attack.max_rounds,
        "success_round": success_round,
        "variants_tried": [p.variant for p in payloads],
        "payload_hashes": [hashlib.sha256(p.text.encode("utf-8")).hexdigest()[:16] for p in payloads],
        "verdict_type": report.verdict.type.value,
        "success": report.verdict.success,
        "evidence": report.verdict.evidence,
        "sink_capture_count": len(captures),
        "flow_entry_count": len(entries),
        "taint_edge_count": len(report.taint_edges),
        "replay_hash": replay_hash(report),
        "wall_ms": wall_ms,
        "artifacts": {
            "flow": "flow.jsonl" if config.defense.proxy else None,
            "sink_capture": "sink_capture.jsonl" if captures else None,
        },
    }
    trajectory = [
        {
            "round": step.round,
            "payload": step.payload,
            "payload_hash": hashlib.sha256(step.payload.encode("utf-8")).hexdigest()[:16],
            "target_response": step.target_response,
            "tool_calls": [c.model_dump() for c in step.tool_calls],
        }
        for step in report.trajectory
    ]
    return Outcome(
        run_id=config.run_id,
        config=config,
        report=report,
        meta=meta,
        latency=_latency_summary(victim.timings_ms, config.defense.proxy),
        trajectory=trajectory,
    )


def negative_control_outcome(config: RunConfig) -> Outcome:
    """N/A 格：不执行攻击，只登记"这一格不适用"，用作攻击引擎误报探针。"""
    generator = AttackGenerator(config.attack)
    first_payload = generator.generate(1).text
    report = Report(
        run_id=config.run_id,
        verdict=n_a_verdict(),
        trajectory=[],
        taint_edges=[],
        metrics=Metrics(latency_overhead_ms={}),
        repro=ReproInfo(
            seed=config.attack.seed,
            engine_version=ENGINE_VERSION,
            payload_hash=hashlib.sha256(first_payload.encode("utf-8")).hexdigest(),
        ),
    )
    meta = {
        "run_id": config.run_id,
        "target": config.target.id,
        "attack_class": config.attack.class_.value,
        "seed": config.attack.seed,
        "defense": "on" if config.defense.proxy else "off",
        "policy": config.defense.policy.value,
        "skipped": "negative_control",
        "reason": f"{config.target.id} 不提供 {config.attack.class_.value} 所需攻击面",
        "success": False,
        "verdict_type": report.verdict.type.value,
        "rounds_used": 0,
        "not_executed_payload_hash": meta_hash(first_payload),
        "replay_hash": replay_hash(report),
    }
    return Outcome(
        run_id=config.run_id,
        config=config,
        report=report,
        meta=meta,
        latency=_latency_summary([], config.defense.proxy),
        trajectory=[],
    )


def meta_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_outcome(out_root: Path, outcome: Outcome, *, subdir: str = RUNS_DIR, attempt: str | None = None) -> Path:
    """落盘一组运行的全部产物（原子覆盖写，重复运行同一 run_id 直接替换）。"""
    dest = Path(out_root) / subdir / outcome.run_id
    if attempt:
        dest = dest / attempt
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "config.json").write_text(outcome.config.model_dump_json(indent=2), encoding="utf-8")
    (dest / "report.json").write_text(outcome.report.model_dump_json(indent=2), encoding="utf-8")
    (dest / "meta.json").write_text(
        json.dumps(outcome.meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (dest / "latency.json").write_text(
        json.dumps(outcome.latency, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_jsonl(dest / "trajectory.jsonl", outcome.trajectory)
    return dest


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def copy_run_artifacts(workdir: Path, dest: Path) -> None:
    """把 flow/sink_capture 从执行工作区搬进 results 目录（analysis 读 flow.jsonl）。"""
    for name in (ws.FLOW_FILE, ws.CAPTURE_FILE, ws.TAINT_FILE):
        src = Path(workdir) / name
        if src.exists():
            (dest / name).write_bytes(src.read_bytes())


async def run_cell(
    cell,
    out_root: Path,
    *,
    work_root: Path | None = None,
    subdir: str = RUNS_DIR,
    attempt: str | None = None,
    run_id: str | None = None,
    **opts: Any,
) -> Outcome:
    """执行一个矩阵格的一次运行（含 N/A 负对照的跳过路径）。

    run_id 覆盖只服务于平台临时运行：产物目录名必须与 RunConfig.run_id 一致，
    否则报告服务按 id 找不到自己的那一份。
    """
    out_root = Path(out_root)
    config = cell.config(run_id=run_id)
    if not cell.applicable:
        outcome = negative_control_outcome(config)
        dest = write_outcome(out_root, outcome, subdir=subdir, attempt=attempt)
        _empty_flow(dest)
        return outcome

    workdir = (Path(work_root) if work_root else out_root.parent / ".work") / config.run_id
    if attempt:
        workdir = workdir / attempt
    prepare_workdir(workdir, config)
    outcome = await execute(config, workdir, **opts)
    dest = write_outcome(out_root, outcome, subdir=subdir, attempt=attempt)
    copy_run_artifacts(workdir, dest)
    return outcome


def _empty_flow(dest: Path) -> None:
    if not (dest / ws.FLOW_FILE).exists():
        (dest / ws.FLOW_FILE).write_text("", encoding="utf-8")


async def run_cells(
    cells: list[Any],
    out_root: Path,
    *,
    jobs: int = 4,
    on_done: Any | None = None,
    **opts: Any,
) -> list[Outcome]:
    """批量执行；每组独立工作区，并发只影响墙钟时间，不影响任何数字。"""
    semaphore = asyncio.Semaphore(max(1, jobs))
    work_root = Path(out_root).parent / ".work"
    done = 0

    async def guarded(cell: Any) -> Outcome:
        nonlocal done
        async with semaphore:
            outcome = await run_cell(cell, out_root, work_root=work_root, **opts)
        done += 1
        if on_done:
            on_done(done, len(cells), outcome)
        return outcome

    return list(await asyncio.gather(*(guarded(cell) for cell in cells)))


# ---- 正常任务套件（误报测试，基准规格 §3）----

NORMAL_SEED = 7


def normal_config(task, entry, *, policy: str = "block") -> RunConfig:
    """正常任务不是攻击：攻击类字段仅用于满足契约，判定固定走负对照。"""
    oracle = oracle_for(entry, NORMAL_SEED)
    return RunConfig(
        run_id=task.run_id,
        target=TargetSpec(
            id=entry.id,
            name=entry.name,
            agent_endpoint=f"http://127.0.0.1:{entry.port}/act",
            mcp_servers=list(entry.mcp_servers),
        ),
        attack=AttackSpec(
            class_=AttackClass.A2_INDIRECT_TOOL_RESULT,
            seed=NORMAL_SEED,
            max_rounds=1,
            carrier=entry.carrier,
            objective_marker=DEFAULT_OBJECTIVE_MARKER,
        ),
        defense=DefenseSpec(proxy=True, policy=policy),
        oracle=OracleSpec(**oracle),
        engine_version=ENGINE_VERSION,
    )


def tool_calls_from_flow(entries: list[dict[str, Any]]) -> list[ToolCallRecord]:
    return [
        ToolCallRecord(
            call_id=str(payload.get("call_id", "")),
            tool=str(payload.get("name", "")),
            args=payload.get("arguments", {}),
            timestamp_ms=int(entry.get("ts_ms", 0)),
        )
        for entry in entries
        if entry.get("direction") == "front_request" and entry.get("method") == "tools/call"
        and (payload := entry.get("payload", {}))
    ]


async def execute_normal(
    task, workdir: Path, *, policy: str = "block", downgrade: bool = True
) -> Outcome:
    """跑一条合法任务：只观察污点层是否误拦，不引入攻击引擎。"""
    entry = range_target(task.target)
    config = normal_config(task, entry, policy=policy)
    prepare_workdir(workdir, config)
    params = victim_params(
        entry,
        workdir,
        defense=True,
        options=ProxyOptions(policy=policy, downgrade_on_untrusted=downgrade, seed=NORMAL_SEED),
    )
    evidence = FileEvidence(workdir)
    async with RangeVictim(params, entry) as victim:
        started = time.perf_counter()
        response = await victim.act(task.text)
        wall_ms = round((time.perf_counter() - started) * 1000, 3)

    captures, entries = evidence.snapshot()
    step = TrajectoryStep(
        round=1,
        payload=task.text,
        target_response=response.text,
        tool_calls=tool_calls_from_flow(entries),
    )
    report = assemble_report(
        config=config,
        engine_version=ENGINE_VERSION,
        verdict=n_a_verdict(),
        trajectory=[step],
        proxy_entries=entries,
        first_payload=task.text,
    )
    blocked_edges = [edge for edge in report.taint_edges if edge.blocked]
    meta = {
        "run_id": config.run_id,
        "target": task.target,
        "task": task.text,
        "note": task.note,
        "intended_flag": task.intended_flag,
        "defense": "on",
        "policy": policy,
        "verdict_type": report.verdict.type.value,
        "success": False,
        "blocked": bool(blocked_edges),
        "alerted": bool(report.taint_edges) and not blocked_edges,
        "taint_edge_count": len(report.taint_edges),
        "blocked_edge_count": len(blocked_edges),
        "tool_calls": [call.tool for call in step.tool_calls],
        "sink_capture_count": len(captures),
        "response": response.text,
        "replay_hash": replay_hash(report),
        "wall_ms": wall_ms,
    }
    return Outcome(
        run_id=config.run_id,
        config=config,
        report=report,
        meta=meta,
        latency=_latency_summary(victim.timings_ms, True),
        trajectory=[
            {
                "round": 1,
                "payload": task.text,
                "payload_hash": meta_hash(task.text),
                "target_response": response.text,
                "tool_calls": [c.model_dump() for c in step.tool_calls],
            }
        ],
    )


async def run_normal_suite(
    out_root: Path,
    tasks: list[Any] | None = None,
    *,
    jobs: int = 4,
    policy: str = "block",
    work_root: Path | None = None,
) -> list[Outcome]:
    from .normal_tasks import all_tasks

    wanted = tasks or all_tasks()
    out_root = Path(out_root)
    work_base = Path(work_root) if work_root else out_root.parent / ".work"
    semaphore = asyncio.Semaphore(max(1, jobs))

    async def guarded(task: Any) -> Outcome:
        async with semaphore:
            workdir = work_base / "normal" / task.run_id
            outcome = await execute_normal(task, workdir, policy=policy)
            dest = write_outcome(out_root, outcome, subdir=NORMAL_DIR)
            copy_run_artifacts(workdir, dest)
            return outcome

    return list(await asyncio.gather(*(guarded(task) for task in wanted)))
