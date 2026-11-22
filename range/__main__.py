"""靶场命令行入口。

    python -m range serve --target T1                 # HTTP 靶标 Agent（默认 9001）
    python -m range serve --target T2 --defense off    # 对照组：不接代理
    python -m range describe                           # 打印靶标目录（前端/文档用）
    python -m range act --target T1 --message "..."    # 单次调用，手工验证受害者行为
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from .specs import TARGETS


def _cmd_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mcpsentry-range serve")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--defense", default="on", choices=["on", "off"])
    parser.add_argument("--policy", default="block", choices=["alert", "block"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--semantic", action="store_true", help="透传 DASHSCOPE_* 给代理语义层")
    parser.add_argument("--paraphrase", action="store_true", help="受害者转述而非复制载荷")
    parser.add_argument("--workdir-root", default=None)
    args = parser.parse_args(argv)

    import uvicorn

    from .agent_app import RangeService, create_app

    workdir_root = Path(args.workdir_root or Path(tempfile.gettempdir()) / "mcpsentry-range")
    service = RangeService(
        args.target,
        workdir_root,
        defense=args.defense == "on",
        policy=args.policy,
        seed=args.seed,
        semantic=args.semantic,
        paraphrase=args.paraphrase,
    )
    port = args.port or TARGETS[args.target.upper()].port
    uvicorn.run(create_app(service), host=args.host, port=port)
    return 0


def _cmd_describe(argv: list[str]) -> int:
    from .agent_app import _target_catalog

    print(json.dumps(_target_catalog(), ensure_ascii=False, indent=2))
    return 0


def _cmd_act(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mcpsentry-range act")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--message", required=True)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--defense", default="on", choices=["on", "off"])
    parser.add_argument("--canary", default="CANARY-00000000")
    parser.add_argument("--carrier", default=None, help="注入正文，写入 external.txt")
    args = parser.parse_args(argv)

    from . import workspace as ws
    from .session import victim_params
    from .victim import RangeVictim

    workdir = Path(args.workdir or Path(tempfile.gettempdir()) / f"mcpsentry-act-{args.target}")
    workdir.mkdir(parents=True, exist_ok=True)
    ws.prepare(workdir, canary=args.canary, run_id="manual")
    if args.carrier:
        private = ws.private_doc_text(args.canary)
        text = f"{private}\n\n{args.carrier}\n"
        ws.write_private_doc(ws.Workspace(workdir), args.canary)
        (workdir / ws.DOCS_DIR / "external.txt").write_text(text, encoding="utf-8")
        (workdir / ws.WEB_DIR / "external.txt").write_text(text, encoding="utf-8")

    params = victim_params(TARGETS[args.target.upper()], workdir, defense=args.defense == "on")

    async def go() -> str:
        async with RangeVictim(params, args.target) as victim:
            return (await victim.act(args.message)).text

    print(asyncio.run(go()))
    print(f"[workdir] {workdir}", file=sys.stderr)
    return 0


_COMMANDS = {"serve": _cmd_serve, "describe": _cmd_describe, "act": _cmd_act}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    handler = _COMMANDS.get(command)
    if handler is None:
        print(f"unknown command {command!r}; choose from {sorted(_COMMANDS)}", file=sys.stderr)
        return 2
    return handler(rest)


if __name__ == "__main__":
    raise SystemExit(main())
