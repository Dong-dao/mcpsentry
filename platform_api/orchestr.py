"""运行编排：把一次平台点击变成一组真实攻击运行。

MVP 用 FastAPI BackgroundTasks + 进程内信号量（技术栈文档 §4：Redis+Celery 是可选）。
两个硬约束：

1. 平台临时运行写 `bench/results/platform/`，绝不覆盖 `runs/` 里的矩阵正式产物——
   D11 之后数字冻结，UI 上随便点也不能改基准。
2. 2 核 4G 的 ECS 上并发跑 MCP 子进程会互相抢 CPU，信号量默认 2；
   并发只影响墙钟时间，不影响任何判定（每组独立工作区）。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.matrix import Cell
from bench.report import build as build_metrics
from bench.runner import run_cell
from range.specs import ATTACK_CLASSES, target

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "bench" / "results"
PLATFORM_SUBDIR = "platform"
WORK_ROOT = RESULTS_ROOT / ".work" / "platform"


@dataclass
class RunRequest:
    target: str = "T1"
    attack_class: str = "A2_indirect_tool_result"
    seed: int = 42
    defense: str = "block"  # off | block | alert
    paraphrase: bool = False
    semantic: bool = False
    note: str = ""

    def validate(self) -> None:
        if self.attack_class not in ATTACK_CLASSES:
            raise ValueError(f"unknown attack_class {self.attack_class!r}; {ATTACK_CLASSES}")
        if self.defense not in ("off", "block", "alert"):
            raise ValueError(f"unknown defense {self.defense!r}")
        target(self.target)  # 未知靶标在这里就抛，别留到子进程里

    def cell(self) -> Cell:
        self.validate()
        return Cell(
            entry=target(self.target),
            attack_class=self.attack_class,
            seed=self.seed,
            defense=self.defense,
        )

    def run_id(self) -> str:
        cls = self.attack_class.split("_", 1)[0]
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        return f"p-{self.target}-{cls}-s{self.seed}-{self.defense}-{stamp}"


class Orchestrator:
    def __init__(self, results_root: Path = RESULTS_ROOT, jobs: int | None = None) -> None:
        self.results_root = Path(results_root)
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.semaphore = asyncio.Semaphore(jobs or int(os.environ.get("MCPSENTRY_JOBS", 2)))
        self.inflight: set[str] = set()

    async def perform(self, run_id: str, req: RunRequest, on_state: Any = None) -> dict[str, Any]:
        """执行一组运行并返回 meta；异常也回报给调用方（历史里留 failed）。"""
        if on_state:
            on_state("running")
        self.inflight.add(run_id)
        try:
            async with self.semaphore:
                outcome = await run_cell(
                    req.cell(),
                    self.results_root,
                    work_root=WORK_ROOT,
                    subdir=PLATFORM_SUBDIR,
                    run_id=run_id,
                    paraphrase=req.paraphrase,
                    semantic=req.semantic,
                )
            if on_state:
                on_state("done", outcome.meta)
            return outcome.meta
        except Exception as exc:  # noqa: BLE001 —— 编排层必须把失败落进历史，不能只 500
            if on_state:
                on_state("failed", {"error": f"{type(exc).__name__}: {exc}"})
            raise
        finally:
            self.inflight.discard(run_id)

    def demo_plan(self, req: RunRequest) -> list[tuple[str, RunRequest]]:
        """一键 demo：同一格跑 off / block 两档，成对展示"没有代理 vs 有代理"。"""
        pairs = []
        for tier in ("off", "block"):
            clone = RunRequest(**{**asdict(req), "defense": tier})
            pairs.append((clone.run_id(), clone))
        return pairs

    def metrics(self) -> dict[str, Any]:
        return build_metrics(self.results_root)
