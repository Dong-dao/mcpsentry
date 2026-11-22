"""平台入口。

    python -m platform_api serve --host 0.0.0.0 --port 8000 --reload
    python -m platform_api build-demo
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .demo import build_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "platform_api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(REPO_ROOT),
    )
    return 0


def cmd_build_demo(_: argparse.Namespace) -> int:
    path = asyncio.run(build_bundle())
    print(f"demo bundle → {path}（{path.stat().st_size // 1024} KB）")
    print("前端零算力可读；随代码一起提交，ECS 冷启动即有内容。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m platform_api", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="启动 API（/docs 有交互式文档）")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)
    demo = sub.add_parser("build-demo", help="生成一键 demo 预置包")
    demo.set_defaults(func=cmd_build_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
