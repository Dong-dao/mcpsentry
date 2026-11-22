"""靶标 Agent 的 HTTP 形态（对齐 engine/attacks/agent.py 的最小契约）。

契约（A 侧 HTTPTargetAgent 按此调用）：
    POST {agent_endpoint}   body {"payload": "<本轮触发语>", "run_id": "..."}
                            → 200 {"response": "<靶标 Agent 文本响应>"}

契约里没有"配置 run""投放注入"两个动作，但真实靶场必须先有这些状态，
所以本服务额外提供 /run、/plant、/reset；A 侧用本地 Planter 时无需调用 /plant。

一个进程服务一个靶标（--target），默认端口见 range/specs.py。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from engine import ENGINE_VERSION
from engine.contracts import AttackClass, AttackSpec, DefenseSpec, RunConfig, TargetSpec

from . import workspace as ws
from .planter import CarrierPlanter
from .session import ProxyOptions, victim_params
from .specs import DEFAULT_OBJECTIVE_MARKER, TARGETS, oracle_for
from .victim import RangeVictim


@dataclass
class LiveRun:
    config: RunConfig
    workdir: Path
    victim: RangeVictim
    planter: CarrierPlanter
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RangeService:
    """把靶标进程、工作区与受害者会话按 run_id 管起来。"""

    def __init__(
        self,
        target_id: str,
        workdir_root: Path,
        *,
        defense: bool = True,
        policy: str = "block",
        seed: int = 42,
        semantic: bool = False,
        paraphrase: bool = False,
    ):
        self.entry = TARGETS[target_id.upper()]
        self.workdir_root = Path(workdir_root)
        self.defense = defense
        self.policy = policy
        self.seed = seed
        self.semantic = semantic
        self.paraphrase = paraphrase
        self.runs: dict[str, LiveRun] = {}

    def config_for(self, run_id: str, canary: str | None = None) -> RunConfig:
        oracle = oracle_for(self.entry, self.seed)
        if canary:
            oracle["canary"] = canary
        return RunConfig(
            run_id=run_id,
            target=TargetSpec(
                id=self.entry.id,
                name=self.entry.name,
                agent_endpoint=f"http://127.0.0.1:{self.entry.port}/act",
                mcp_servers=list(self.entry.mcp_servers),
            ),
            attack=AttackSpec(
                class_=AttackClass.A2_INDIRECT_TOOL_RESULT,
                seed=self.seed,
                carrier=self.entry.carrier,
                objective_marker=DEFAULT_OBJECTIVE_MARKER,
            ),
            defense=DefenseSpec(proxy=self.defense, policy=self.policy),
            oracle=oracle,
            engine_version=ENGINE_VERSION,
        )

    async def open_run(self, config: RunConfig) -> LiveRun:
        if existing := self.runs.get(config.run_id):
            return existing
        workdir = self.workdir_root / config.run_id
        workdir.mkdir(parents=True, exist_ok=True)
        ws.prepare(workdir, canary=config.oracle.canary, run_id=config.run_id)
        (workdir / "config.json").write_text(config.model_dump_json(indent=2), encoding="utf-8")
        params = victim_params(
            self.entry,
            workdir,
            defense=config.defense.proxy,
            options=ProxyOptions(
                policy=config.defense.policy.value,
                downgrade_on_untrusted=config.defense.downgrade_on_untrusted,
                seed=self.seed,
                semantic=self.semantic,
            ),
        )
        victim = RangeVictim(params, self.entry.id, paraphrase=self.paraphrase)
        await victim.__aenter__()
        live = LiveRun(
            config=config, workdir=workdir, victim=victim, planter=CarrierPlanter(config, workdir)
        )
        self.runs[config.run_id] = live
        return live

    async def close_run(self, run_id: str) -> None:
        live = self.runs.pop(run_id, None)
        if live is not None:
            await live.victim.__aexit__(None, None, None)

    async def close_all(self) -> None:
        for run_id in list(self.runs):
            await self.close_run(run_id)

    async def act(self, run_id: str, message: str) -> str:
        live = await self.open_run(self.config_for(run_id))
        async with live.lock:
            return (await live.victim.act(message)).text

    def plant(self, live: LiveRun, text: str, round_no: int, attack_class: str | None) -> None:
        if attack_class:
            live.config.attack.class_ = AttackClass(attack_class)
        live.planter.plant(_RemotePayload(text), round_no)


class _RemotePayload:
    """远程投放只需要 text；与引擎 Payload 的结构化子集兼容。"""

    def __init__(self, text: str):
        self.text = text
        self.variant = "remote"
        self.a3_marker = None


class ActRequest(BaseModel):
    payload: str
    run_id: str = "default"


class RunRequest(BaseModel):
    run_id: str
    canary: str | None = None
    defense: bool | None = None
    policy: str | None = None
    attack_class: str | None = None


class PlantRequest(BaseModel):
    run_id: str
    text: str
    round: int = 1
    attack_class: str | None = None


def _target_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "port": t.port,
            "vulnerability": t.vulnerability,
            "mcp_servers": list(t.mcp_servers),
            "sinks": list(t.sinks),
            "carrier": t.carrier,
            "hardened": t.hardened,
            "applicable_attacks": list(t.applicable),
            "description": t.description,
        }
        for t in TARGETS.values()
    ]


def create_app(service: RangeService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await service.close_all()

    app = FastAPI(title=f"MCPSentry range · {service.entry.id}", version="1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "target": service.entry.id,
            "name": service.entry.name,
            "defense": service.defense,
            "open_runs": sorted(service.runs),
        }

    @app.get("/targets")
    async def targets() -> list[dict[str, Any]]:
        return _target_catalog()

    @app.post("/run")
    async def open_run(req: RunRequest) -> dict[str, Any]:
        config = service.config_for(req.run_id, canary=req.canary)
        if req.defense is not None:
            config.defense.proxy = req.defense
        if req.policy:
            config.defense.policy = req.policy  # type: ignore[arg-type]
        if req.attack_class:
            config.attack.class_ = AttackClass(req.attack_class)
        live = await service.open_run(config)
        return {
            "run_id": live.config.run_id,
            "workdir": str(live.workdir),
            "canary": live.config.oracle.canary,
            "defense": live.config.defense.proxy,
        }

    @app.post("/act")
    async def act(req: ActRequest) -> dict[str, str]:
        return {"response": await service.act(req.run_id, req.payload)}

    @app.post("/plant")
    async def plant(req: PlantRequest) -> dict[str, Any]:
        live = service.runs.get(req.run_id)
        if live is None:
            raise HTTPException(
                status_code=409, detail=f"run {req.run_id} not opened; call /run or /act first"
            )
        service.plant(live, req.text, req.round, req.attack_class)
        return {"planted": True, "run_id": req.run_id, "round": req.round}

    @app.post("/reset")
    async def reset(run_id: str = "default") -> dict[str, Any]:
        live = service.runs.get(run_id)
        if live is not None:
            live.planter.reset()
            store = ws.Workspace(live.workdir)
            for path in (store.capture, store.flow, store.taint_log):
                path.unlink(missing_ok=True)
            ws.write_private_doc(store, live.config.oracle.canary)
        return {"reset": run_id}

    return app
