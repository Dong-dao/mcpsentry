"""一次运行的进程装配：受害者连的是代理还是裸后端，全在这里决定。

防御 off → 受害者直连 range/backend.py
防御 on  → 受害者连 `python -m engine.proxy`，代理内部 spawn 同一个后端

env 说明：mcp SDK spawn 子进程只透传白名单变量（PATH/PATHEXT…），PYTHONPATH 不在其中，
因此这里显式补上仓库根目录，并固定 cwd，保证跨机器行为一致。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from mcp import StdioServerParameters

from . import workspace as ws
from .specs import TargetSpecEntry

REPO_ROOT = Path(__file__).resolve().parent.parent


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = f"{REPO_ROOT}{os.pathsep}{existing}" if existing else str(REPO_ROOT)
    env = {"PYTHONPATH": pythonpath, "PYTHONIOENCODING": "utf-8"}
    if extra:
        env.update(extra)
    return env


def backend_cmd(profile: str, workdir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "range.backend",
        "--profile",
        profile,
        "--workdir",
        str(Path(workdir)),
    ]


@dataclass(frozen=True)
class ProxyOptions:
    policy: str = "block"
    downgrade_on_untrusted: bool = True
    seed: int | None = 42
    semantic: bool = False

    def env(self) -> dict[str, str] | None:
        if not self.semantic:
            return None
        # 语义层由代理内部按 DASHSCOPE_API_KEY 自动开关；runner 不猜 key，只透传
        import os

        extra = {}
        for key in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "DASHSCOPE_MODEL"):
            if os.environ.get(key):
                extra[key] = os.environ[key]
        return extra or None


def victim_params(
    entry: TargetSpecEntry,
    workdir: Path,
    *,
    defense: bool,
    options: ProxyOptions | None = None,
) -> StdioServerParameters:
    """构造受害者侧的 MCP 连接参数（代理与否对受害者透明）。"""
    opts = options or ProxyOptions()
    workdir = Path(workdir)
    if not defense:
        cmd = backend_cmd(entry.profile, workdir)
        return StdioServerParameters(
            command=cmd[0], args=cmd[1:], env=_child_env(), cwd=str(REPO_ROOT)
        )

    classes = json.loads(json.dumps(entry.tool_classes))
    ws_root = workdir
    ws_root.mkdir(parents=True, exist_ok=True)
    (ws_root / ws.CLASSES_FILE).write_text(json.dumps(classes, ensure_ascii=False), encoding="utf-8")

    args = [
        "-m",
        "engine.proxy",
        "--backend",
        json.dumps(backend_cmd(entry.profile, workdir)),
        "--log",
        str(workdir / ws.FLOW_FILE),
        "--taint-log",
        str(workdir / ws.TAINT_FILE),
        "--classes",
        str(workdir / ws.CLASSES_FILE),
        "--policy",
        opts.policy,
        "--downgrade-on-untrusted" if opts.downgrade_on_untrusted else "--no-downgrade-on-untrusted",
        "--name",
        f"mcpsentry-proxy-{entry.profile}",
    ]
    if opts.seed is not None:
        args += ["--seed", str(opts.seed)]
    return StdioServerParameters(
        command=sys.executable, args=args, env=_child_env(opts.env()), cwd=str(REPO_ROOT)
    )
