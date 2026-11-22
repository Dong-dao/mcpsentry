"""bench 命令行入口（成员 B 的 D9 执行器）。

    python -m bench matrix  --out bench/results --jobs 6      # 120 组
    python -m bench normal  --out bench/results               # 50 条正常任务
    python -m bench replay  --out bench/results --sample 12   # 回放一致率
    python -m bench summary --out bench/results               # 复算交数

复用 A 的 engine/attack/判定，本入口只负责选格、并发与落盘；任何数字都不在这里
产生，summary 一律走 engine.analysis。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import report as bench_report
from . import runner
from .matrix import Cell, ablation_cells, describe, matrix
from .normal_tasks import all_tasks
from range.specs import ATTACK_CLASSES, SEEDS, target

RUN_ID_RE = re.compile(r"^r-(T\d)-(\w+)-s(\d+)-(off|block|alert)$")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = REPO_ROOT / "bench" / "results"
DEFAULT_METRICS = REPO_ROOT / "bench" / "metrics"


def parse_run_id(run_id: str) -> Cell:
    m = RUN_ID_RE.match(run_id)
    if not m:
        raise SystemExit(
            f"bad run_id {run_id!r}; expected r-<T#>-<attack_class>-s<seed>-<off|block|alert>"
        )
    return Cell(entry=target(m.group(1)), attack_class=m.group(2), seed=int(m.group(3)), defense=m.group(4))


def selected_cells(args: argparse.Namespace) -> list[Cell]:
    cells = ablation_cells(name=args.ablation) if args.ablation else matrix(tuple(args.tiers.split(",")))
    if args.targets:
        wanted = {t.strip().upper() for t in args.targets.split(",")}
        cells = [c for c in cells if c.entry.id in wanted]
    if args.classes:
        wanted = {c.strip() for c in args.classes.split(",")}
        for cls in wanted:
            if cls not in ATTACK_CLASSES:
                raise SystemExit(f"unknown attack class {cls!r}; {ATTACK_CLASSES}")
        cells = [c for c in cells if c.attack_class in wanted]
    if args.seeds:
        wanted = {int(s) for s in args.seeds.split(",")}
        cells = [c for c in cells if c.seed in wanted]
    if not cells:
        raise SystemExit("filter selected 0 cells")
    return cells


def _tracker(stream):
    def on_done(i: int, total: int, outcome: runner.Outcome) -> None:
        meta = outcome.meta
        print(
            f"[{i}/{total}] {outcome.run_id} → {meta['verdict_type']}"
            f" success={int(meta['success'])} rounds={meta.get('rounds_used', 0)}",
            file=stream,
            flush=True,
        )

    return on_done


def _opts(args: argparse.Namespace) -> dict:
    return {"paraphrase": args.paraphrase, "semantic": args.semantic}


async def cmd_matrix(args: argparse.Namespace) -> int:
    cells = selected_cells(args)
    print(f"matrix: {json.dumps(describe(cells), ensure_ascii=False)}", flush=True)
    outcomes = await runner.run_cells(
        cells, args.out, jobs=args.jobs, on_done=_tracker(sys.stderr), **_opts(args)
    )
    _print_totals(outcomes)
    return 0


async def cmd_normal(args: argparse.Namespace) -> int:
    tasks = all_tasks()
    if args.targets:
        wanted = {t.strip().upper() for t in args.targets.split(",")}
        tasks = [t for t in tasks if t.target in wanted]
    outcomes = await runner.run_normal_suite(args.out, tasks, jobs=args.jobs, policy=args.policy)
    blocked = sum(1 for o in outcomes if o.meta.get("blocked"))
    print(f"normal: {len(outcomes)} 条，拦截 {blocked} 条", flush=True)
    return 0


async def cmd_single(args: argparse.Namespace) -> int:
    if args.run_id:
        cell = parse_run_id(args.run_id)
    else:
        if not (args.target and args.attack_class):
            raise SystemExit("single needs --run-id or (--target and --class)")
        cell = Cell(
            entry=target(args.target),
            attack_class=args.attack_class,
            seed=args.seed,
            defense=args.defense,
        )
    outcome = await runner.run_cell(cell, args.out, **_opts(args))
    print(json.dumps(outcome.meta, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return 0


async def cmd_replay(args: argparse.Namespace) -> int:
    """重跑同一 RunConfig，产物落 replays/<run_id>/<attempt>/，只用于比对 replay_hash。"""
    runs_dir = args.out / "runs"
    if not runs_dir.exists():
        raise SystemExit(f"{runs_dir} 不存在——先跑 matrix")
    candidates = sorted(child.name for child in runs_dir.iterdir() if (child / "config.json").exists())
    if args.run_ids:
        candidates = [r for r in candidates if r in set(args.run_ids.split(","))]
    chosen = candidates if args.sample <= 0 else _spread(candidates, args.sample)
    print(f"replay: {len(chosen)} 组 × {args.attempts} 次", flush=True)

    work_root = args.out / ".work" / "replay"
    for run_id in chosen:
        cell = parse_run_id(run_id)
        for attempt in range(1, args.attempts + 1):
            outcome = await runner.run_cell(
                cell,
                args.out,
                work_root=work_root,
                subdir=runner.REPLAY_DIR,
                attempt=str(attempt),
                **_opts(args),
            )
            print(f"  {run_id} #{attempt} → {outcome.meta['replay_hash'][:12]}", flush=True)
    return 0


def _spread(names: list[str], k: int) -> list[str]:
    """分层抽样：按 (防御档, 靶标) 分桶轮流取，避免整批落在同一档或同一靶标。"""
    if k >= len(names):
        return names
    buckets: dict[tuple[str, str], list[str]] = {}
    for name in names:
        tier, target_id = name.rsplit("-", 1)[-1], name.split("-", 2)[1]
        buckets.setdefault((tier, target_id), []).append(name)
    order = sorted(buckets)
    picked: list[str] = []
    while len(picked) < k:
        for key in order:
            if buckets[key]:
                picked.append(buckets[key].pop(0))
                if len(picked) == k:
                    break
    return sorted(picked)


def _print_totals(outcomes: list[runner.Outcome]) -> None:
    executed = [o for o in outcomes if o.meta.get("skipped") != "negative_control"]
    print(
        f"\ntotal {len(outcomes)} | executed {len(executed)} "
        f"| negative_control {len(outcomes) - len(executed)} "
        f"| success {sum(1 for o in outcomes if o.success)}",
        flush=True,
    )


def cmd_summary(args: argparse.Namespace) -> int:
    payload = bench_report.build(args.out, metrics_dir=args.metrics)
    if args.json:
        print(json.dumps(payload["canonical"], ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print((args.metrics / "summary.md").read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m bench", description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS, help="results 根目录")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS, help="summary 落盘目录")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--jobs", type=int, default=4)
    common.add_argument("--targets", default="", help="逗号分隔，如 T1,T5")
    common.add_argument("--paraphrase", action="store_true", help="E1：受害者转述而非复制")
    common.add_argument("--semantic", action="store_true", help="E3：开启代理语义层（需 DASHSCOPE_API_KEY）")

    m = sub.add_parser("matrix", parents=[common], help="跑基准矩阵")
    m.add_argument("--tiers", default="off,block")
    m.add_argument("--classes", default="", help="逗号分隔的攻击类")
    m.add_argument("--seeds", default="", help="逗号分隔的种子")
    m.add_argument("--ablation", default="", help="E4：用消融小矩阵替代全量")
    m.set_defaults(func=cmd_matrix)

    n = sub.add_parser("normal", parents=[common], help="50 条正常任务（误报）")
    n.add_argument("--policy", default="block")
    n.set_defaults(func=cmd_normal)

    s = sub.add_parser("single", parents=[common], help="单组运行，联调用")
    s.add_argument("--run-id", default="")
    s.add_argument("--target", default="")
    s.add_argument("--class", dest="attack_class", default="")
    s.add_argument("--seed", type=int, default=SEEDS[0])
    s.add_argument("--defense", default="off", choices=["off", "block", "alert"])
    s.set_defaults(func=cmd_single)

    r = sub.add_parser("replay", parents=[common], help="回放一致率")
    r.add_argument("--sample", type=int, default=12, help="0 = 全部")
    r.add_argument("--attempts", type=int, default=2)
    r.add_argument("--run-ids", default="", help="逗号分隔，指定重放组")
    r.set_defaults(func=cmd_replay)

    sm = sub.add_parser("summary", help="复算指标并写 metrics/summary.{json,md}")
    sm.add_argument("--json", action="store_true", help="只打 canonical 段")
    sm.set_defaults(func=cmd_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.out = args.out.resolve()
    args.metrics = args.metrics.resolve()
    result = args.func(args)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


if __name__ == "__main__":
    raise SystemExit(main())
