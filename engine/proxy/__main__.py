"""命令行入口。

用法：
    python -m engine.proxy --backend '["python","backend.py"]' [--log path]
                           [--taint-log path] [--classes path/to/classes.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .server import run_proxy


def _load_json(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcpsentry-proxy")
    parser.add_argument("--backend", required=True, help='JSON list: ["cmd", "arg1", ...]')
    parser.add_argument("--log", default="logs/flow.jsonl")
    parser.add_argument("--taint-log", default=None, help="污点存储 JSONL 落盘路径（轨迹审计）")
    parser.add_argument(
        "--classes",
        default=None,
        help="工具分类覆盖 JSON 文件：{\"tool\": \"source|sink|neutral\"}",
    )
    parser.add_argument("--name", default="mcpsentry-proxy")
    args = parser.parse_args()

    backend_cmd = json.loads(args.backend)
    if not isinstance(backend_cmd, list) or not backend_cmd:
        parser.error("--backend must be a non-empty JSON list")

    tool_classes = _load_json(args.classes) if args.classes else None
    asyncio.run(
        run_proxy(
            backend_cmd,
            log_path=args.log,
            taint_log_path=args.taint_log,
            tool_classes=tool_classes,
            name=args.name,
        )
    )


if __name__ == "__main__":
    main()
