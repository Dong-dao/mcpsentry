"""命令行入口：python -m engine.proxy --backend '["python","backend.py"]' [--log path]"""

from __future__ import annotations

import argparse
import asyncio
import json

from .server import run_proxy


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcpsentry-proxy")
    parser.add_argument("--backend", required=True, help='JSON list: ["cmd", "arg1", ...]')
    parser.add_argument("--log", default="logs/flow.jsonl")
    parser.add_argument("--name", default="mcpsentry-proxy")
    args = parser.parse_args()

    backend_cmd = json.loads(args.backend)
    if not isinstance(backend_cmd, list) or not backend_cmd:
        parser.error("--backend must be a non-empty JSON list")

    asyncio.run(run_proxy(backend_cmd, log_path=args.log, name=args.name))


if __name__ == "__main__":
    main()
