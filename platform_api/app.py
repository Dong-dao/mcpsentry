"""FastAPI 后端（B 的平台层）。

给前端的只有六个读接口 + 三个写接口，全部围绕 `bench/results` 的原始产物；
判定、指标、复算一律在 engine/bench 侧，这里不复制第二套安全逻辑。

    GET  /api/health              存活 + 产物就绪情况
    GET  /api/targets             靶标注册表（前端选择器）
    GET  /api/metrics             基准指标（bench/metrics/summary.json）
    GET  /api/runs                运行历史（SQLite 索引，分页/过滤）
    GET  /api/runs/{id}           单组详情：config/report/轨迹/污点图
    GET  /api/runs/{id}/export    导出 json|md|html
    POST /api/runs                发起一组运行（后台执行，立刻回 run_id）
    POST /api/demo                一键 demo：同格 off/block 成对运行
    POST /api/matrix              批量跑格（默认只跑筛选出的子集，需显式 confirm）
    GET  /api/custom/example      自定义 MCP 接入的配置样例
    POST /api/custom/probe        探测上传命令的 tools/list（需服务端显式开启）
    POST /api/custom/runs         上传配置跑自己的 MCP 工具链（需服务端显式开启）

写接口是算力开关，默认只允许同源访问（CORS 由 MCPSENTRY_ORIGINS 显式打开），
公网部署必须放在 Caddy 之后并按 deploy/README 收紧。
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, field_validator

from bench.matrix import describe, matrix
from range.specs import ATTACK_CLASSES, SEEDS, TARGETS
from range.specs import target as range_target

from . import custom as custom_api
from . import export, history, reports
from .orchestr import PLATFORM_SUBDIR, RESULTS_ROOT, Orchestrator, RunRequest

REPO_ROOT = Path(__file__).resolve().parent.parent
METRICS_FILE = REPO_ROOT / "bench" / "metrics" / "summary.json"
DEMO_DIR = Path(__file__).resolve().parent / "demo"
_DEFENSES = ("off", "block", "alert", "strict")


class RunBody(BaseModel):
    target: str = "T1"
    attack_class: str = "A2_indirect_tool_result"
    seed: int = 42
    defense: str = "block"
    paraphrase: bool = False
    semantic: bool = False
    note: str = ""

    @field_validator("defense")
    @classmethod
    def _valid_defense(cls, value: str) -> str:
        if value not in _DEFENSES:
            raise ValueError("defense 只能是 off / block / alert / strict")
        return value

    def to_request(self) -> RunRequest:
        return RunRequest(**self.model_dump())


class MatrixBody(BaseModel):
    targets: list[str] = ["T1"]
    classes: list[str] = ["A2_indirect_tool_result"]
    seeds: list[int] = list(SEEDS)
    tiers: list[str] = ["off", "block"]
    confirm: bool = False

    @field_validator("tiers")
    @classmethod
    def _valid_tiers(cls, values: list[str]) -> list[str]:
        bad = [t for t in values if t not in _DEFENSES]
        if bad:
            raise ValueError("tiers 只能包含 off / block / alert / strict")
        return values


def _demo_bundle() -> dict[str, Any] | None:
    """预置运行包：ECS 冷启动或算力被占时，评委依然能点开看到完整报告。"""
    path = DEMO_DIR / "t1-a2-pair.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = history.connect()
    app.state.db = conn
    app.state.orchestrator = Orchestrator()
    if history.stats(conn)["runs"] == 0:
        history.import_existing(conn, RESULTS_ROOT)
    yield
    conn.close()


app = FastAPI(
    title="MCPSentry platform",
    version="1.0.0",
    description="MCP 工具链污点评测平台后端（靶场 + 矩阵 + 报告）",
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.environ.get("MCPSENTRY_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"]
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "results_root": str(RESULTS_ROOT),
        "runs_present": (RESULTS_ROOT / "runs").exists(),
        "metrics_bundled": METRICS_FILE.exists(),
        "demo_bundled": _demo_bundle() is not None,
        "history": history.stats(app.state.db),
    }


@app.get("/api/targets")
def targets() -> dict[str, Any]:
    return {
        "targets": [
            {
                "id": t.id,
                "name": t.name,
                "profile": t.profile,
                "port": t.port,
                "vulnerability": t.vulnerability,
                "description": t.description,
                "sinks": list(t.sinks),
                "mcp_servers": list(t.mcp_servers),
                "hardened": t.hardened,
                "applicable": [c for c in ATTACK_CLASSES if t.is_applicable(c)],
                "na": [c for c in ATTACK_CLASSES if not t.is_applicable(c)],
            }
            for t in TARGETS.values()
        ],
        "attack_classes": list(ATTACK_CLASSES),
        "seeds": list(SEEDS),
        "matrix": describe(matrix()),
    }


@app.get("/api/metrics")
def metrics(refresh: bool = Query(False, description="忽略缓存，从 results/ 重新复算")) -> dict[str, Any]:
    if not refresh and METRICS_FILE.exists():
        return json.loads(METRICS_FILE.read_text(encoding="utf-8"))
    try:
        return app.state.orchestrator.metrics()
    except Exception as exc:  # noqa: BLE001 —— 指标复算失败要能降级到 bundled 文件
        if METRICS_FILE.exists():
            return {"error": str(exc), **json.loads(METRICS_FILE.read_text(encoding="utf-8"))}
        raise HTTPException(500, f"metrics unavailable: {exc}") from None


@app.get("/api/runs")
def runs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    target: str | None = None,
    attack_class: str | None = None,
    defense: str | None = None,
) -> dict[str, Any]:
    rows = history.list_runs(
        app.state.db, limit=limit, offset=offset, target=target,
        attack_class=attack_class, defense=defense,
    )
    return {"items": rows, "limit": limit, "offset": offset, "stats": history.stats(app.state.db)}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    detail = reports.load_run(RESULTS_ROOT, run_id)
    if not detail:
        raise HTTPException(404, f"no artifacts for run {run_id}")
    detail["history"] = history.get_run(app.state.db, run_id)
    return detail


@app.get("/api/runs/{run_id}/export")
def run_export(run_id: str, format: str = Query("md", pattern="^(json|md|html)$")) -> Response:
    detail = reports.load_run(RESULTS_ROOT, run_id)
    if not detail:
        raise HTTPException(404, f"no artifacts for run {run_id}")
    body = export.render(detail, format)
    if format == "html":
        return HTMLResponse(body)
    filename = f"{run_id}.{format}"
    return Response(
        body,
        media_type=export.CONTENT_TYPE[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _state_hooks(run_id: str):
    conn = app.state.db

    def on_state(status: str, meta: dict[str, Any] | None = None) -> None:
        if status == "running":
            history.mark_status(conn, run_id, "running")
        elif status == "done":
            history.record_run(conn, meta or {}, source="platform", status="done")
        else:
            history.mark_status(conn, run_id, status, error=(meta or {}).get("error"))

    return on_state


@app.get("/api/custom/example")
def custom_example() -> dict[str, Any]:
    """给前端「填入样例」按钮用；开关未打开时同样拒绝，避免误导。"""
    try:
        custom_api.ensure_enabled()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    return custom_api.example_body()


@app.post("/api/custom/probe")
async def probe_custom_tools(body: custom_api.CustomProbeBody) -> dict[str, Any]:
    """探测用户 MCP 命令的工具清单；不执行工具调用，失败统一中文通用文案。

    422：未启用 / 命令不合法 / 未 confirm；504：探测超时；502：初始化失败。
    """
    try:
        custom_api.ensure_enabled()
        return await custom_api.probe_command(body)
    except PermissionError as exc:
        raise HTTPException(422, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from None


@app.post("/api/custom/runs", status_code=202)
async def start_custom_run(
    body: custom_api.CustomRunBody, background: BackgroundTasks
) -> dict[str, Any]:
    """上传模板 + 工具清单（可选 command），按内置靶标同样的链路跑一组攻击。

    不传 command 时执行体仍是平台内置 range.backend；传 command 时在白名单内
    执行用户自己的 stdio MCP server。服务端未设 MCPSENTRY_ALLOW_CUSTOM=1 时直接 403。
    """
    try:
        custom_api.ensure_enabled()
        entry = custom_api.build_entry(body)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    req = RunRequest(**custom_api.request_payload(entry, body))
    run_id = custom_api.run_id(entry, body)
    history.mark_queued(app.state.db, asdict(req), run_id)
    background.add_task(app.state.orchestrator.perform, run_id, req, _state_hooks(run_id))
    return {
        "run_id": run_id,
        "status": "queued",
        "target": entry.id,
        "name": entry.name,
        "config": asdict(req),
    }


@app.post("/api/runs", status_code=202)
async def start_run(body: RunBody, background: BackgroundTasks) -> dict[str, Any]:
    try:
        req = body.to_request()
        req.validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    run_id = req.run_id()
    history.mark_queued(app.state.db, asdict(req), run_id)
    background.add_task(app.state.orchestrator.perform, run_id, req, _state_hooks(run_id))
    return {"run_id": run_id, "status": "queued", "config": asdict(req)}


@app.post("/api/demo", status_code=202)
async def start_demo(body: RunBody, background: BackgroundTasks) -> dict[str, Any]:
    req = body.to_request()
    try:
        req.validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    ids = []
    for run_id, pair in app.state.orchestrator.demo_plan(req):
        history.mark_queued(app.state.db, asdict(pair), run_id)
        background.add_task(app.state.orchestrator.perform, run_id, pair, _state_hooks(run_id))
        ids.append({"run_id": run_id, "defense": pair.defense})
    return {"status": "queued", "runs": ids}


@app.get("/api/demo/preset")
def preset_demo() -> dict[str, Any]:
    bundle = _demo_bundle()
    if not bundle:
        raise HTTPException(404, "demo bundle 未生成：python -m platform.build_demo")
    return bundle


@app.post("/api/matrix", status_code=202)
async def start_matrix(body: MatrixBody, background: BackgroundTasks) -> dict[str, Any]:
    """批量跑格。矩阵是全项目的证据底座，所以必须显式 confirm，避免前端误点覆盖产物。"""
    if not body.confirm:
        raise HTTPException(400, "批量运行需要 confirm=true")
    for t in body.targets:
        range_target(t)
    cells = [
        c
        for c in matrix(tuple(body.tiers))
        if c.entry.id in set(body.targets)
        and c.attack_class in set(body.classes)
        and c.seed in set(body.seeds)
    ]
    if not cells:
        raise HTTPException(422, "筛选条件命中 0 格")
    background.add_task(_run_cells, cells)
    return {"status": "queued", "cells": len(cells)}


async def _run_cells(cells: list[Any]) -> dict[str, int]:
    from bench.runner import run_cells

    outcomes = await run_cells(cells, RESULTS_ROOT, jobs=2)
    for outcome in outcomes:
        history.record_run(app.state.db, outcome.meta, source="bench", status="done")
    return {"done": len(outcomes)}


@app.get("/", response_class=PlainTextResponse)
def index() -> str:
    return "MCPSentry platform API. See /docs\n"
