"""矩阵定义（基准规格 §1）：5 靶标 × 4 攻击类 × 3 种子 × 2 防御档 = 120 组。

不适用格（T3/T4 的非 A3 攻击类）作为负对照计入 120：runner 只落盘 config 与
`n_a_negative_control` verdict，绝不执行攻击——执行了就可能造出成功证据，
负对照就失去"攻击引擎误报探针"的意义。
"""

from __future__ import annotations

from dataclasses import dataclass

from engine import ENGINE_VERSION
from engine.contracts import AttackClass, AttackSpec, DefenseSpec, OracleSpec, RunConfig, TargetSpec

from range.specs import (
    ATTACK_CLASSES,
    DEFAULT_OBJECTIVE_MARKER,
    SEEDS,
    TARGETS,
    TargetSpecEntry,
    oracle_for,
)


@dataclass(frozen=True)
class Cell:
    entry: TargetSpecEntry
    attack_class: str
    seed: int
    defense: str  # off | block | alert | strict（矩阵正式档仍只有 off/block）

    @property
    def applicable(self) -> bool:
        return self.entry.is_applicable(self.attack_class)

    @property
    def run_id(self) -> str:
        tier = self.defense
        return f"r-{self.entry.id}-{self.attack_class}-s{self.seed}-{tier}"

    @property
    def short_class(self) -> str:
        return self.attack_class.split("_", 1)[0]

    def config(self, *, downgrade: bool = True, run_id: str | None = None) -> RunConfig:
        """run_id 可覆盖：平台临时运行要独立目录，但格定义与矩阵格完全一致。"""
        proxy = self.defense != "off"
        oracle = oracle_for(self.entry, self.seed)
        return RunConfig(
            run_id=run_id or self.run_id,
            target=TargetSpec(
                id=self.entry.id,
                name=self.entry.name,
                agent_endpoint=f"http://127.0.0.1:{self.entry.port}/act",
                mcp_servers=list(self.entry.mcp_servers),
            ),
            attack=AttackSpec(
                class_=AttackClass(self.attack_class),
                seed=self.seed,
                max_rounds=MAX_ROUNDS,
                carrier=self.entry.carrier,
                objective_marker=DEFAULT_OBJECTIVE_MARKER,
            ),
            defense=DefenseSpec(
                proxy=proxy,
                policy=self.defense if proxy else "block",
                downgrade_on_untrusted=downgrade,
            ),
            oracle=OracleSpec(**oracle),
            engine_version=ENGINE_VERSION,
        )


MAX_ROUNDS = 6


def matrix(defense_tiers: tuple[str, ...] = ("off", "block")) -> list[Cell]:
    """完整 120 组（20 格 × 3 种子 × 2 防御档）。"""
    return [
        Cell(entry=entry, attack_class=cls, seed=seed, defense=tier)
        for entry in TARGETS.values()
        for cls in ATTACK_CLASSES
        for seed in SEEDS
        for tier in defense_tiers
    ]


def ablation_cells(
    *,
    name: str,
    targets: tuple[str, ...] = ("T1", "T2"),
    classes: tuple[str, ...] = ("A2_indirect_tool_result", "A4_exfiltration_inducement"),
    seeds: tuple[int, ...] = SEEDS,
) -> list[Cell]:
    """消融实验用的小矩阵（E1/E3/E4 复用同一批格，只改 runner 开关）。"""
    return [
        Cell(entry=TARGETS[t], attack_class=cls, seed=seed, defense="alert")
        for t in targets
        for cls in classes
        for seed in seeds
    ]


def describe(cells: list[Cell]) -> dict[str, int]:
    return {
        "total": len(cells),
        "applicable": sum(1 for c in cells if c.applicable),
        "negative_control": sum(1 for c in cells if not c.applicable),
    }
