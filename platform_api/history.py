"""运行历史（SQLite，MVP）。

只存"索引 + 判定摘要"，正文一律留在 `bench/results/<run_id>/` 的原始产物里：
数据库不该成为第二份真相，导出的报告也从文件系统读。技术栈文档 §11 明确
"时间不够就砍 Postgres"，这里连 ORM 都没上——一张表、四个查询。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "platform_api" / "data" / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    target       TEXT NOT NULL,
    attack_class TEXT NOT NULL,
    seed         INTEGER NOT NULL,
    defense      TEXT NOT NULL,
    policy       TEXT,
    verdict      TEXT,
    success      INTEGER,
    rounds_used  INTEGER,
    replay_hash  TEXT,
    source       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'done',
    error        TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_created_at ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS runs_target ON runs (target, attack_class);
"""


def db_path(override: Path | str | None = None) -> Path:
    return Path(override or os.environ.get("MCPSENTRY_DB") or DEFAULT_DB)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = db_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_run(
    conn: sqlite3.Connection,
    meta: dict[str, Any],
    *,
    source: str = "platform",
    note: str = "",
    status: str = "done",
    error: str | None = None,
) -> None:
    """落一条运行摘要；同一 run_id 重跑覆盖（可复现性要求它本来就该一致）。"""
    now = _utcnow()
    conn.execute(
        """INSERT INTO runs (run_id, target, attack_class, seed, defense, policy,
                             verdict, success, rounds_used, replay_hash, source,
                             status, error, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_id) DO UPDATE SET
             verdict=excluded.verdict, success=excluded.success,
             rounds_used=excluded.rounds_used, replay_hash=excluded.replay_hash,
             source=excluded.source, status=excluded.status, error=excluded.error,
             note=excluded.note, updated_at=excluded.updated_at""",
        (
            meta.get("run_id"),
            meta.get("target"),
            meta.get("attack_class"),
            meta.get("seed"),
            meta.get("defense"),
            meta.get("policy"),
            meta.get("verdict_type"),
            int(bool(meta.get("success"))),
            int(meta.get("rounds_used") or 0),
            meta.get("replay_hash"),
            source,
            status,
            error,
            note,
            now,
            now,
        ),
    )
    conn.commit()


def mark_queued(conn: sqlite3.Connection, req: dict[str, Any], run_id: str) -> None:
    """排队即入库：UI 要能在结果落地前就显示"这一组在跑"。"""
    now = _utcnow()
    conn.execute(
        """INSERT INTO runs (run_id, target, attack_class, seed, defense, policy,
                             source, status, note, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'platform', 'queued', ?, ?, ?)
           ON CONFLICT(run_id) DO UPDATE SET status='queued', updated_at=excluded.updated_at""",
        (
            run_id,
            req["target"],
            req["attack_class"],
            req["seed"],
            req["defense"],
            req.get("policy"),
            req.get("note", ""),
            now,
            now,
        ),
    )
    conn.commit()


def mark_status(
    conn: sqlite3.Connection, run_id: str, status: str, *, error: str | None = None
) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
        (status, error, _utcnow(), run_id),
    )
    conn.commit()


def list_runs(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    target: str | None = None,
    attack_class: str | None = None,
    defense: str | None = None,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    for col, val in (("target", target), ("attack_class", attack_class), ("defense", defense)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    total, succeeded = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(success), 0) FROM runs"
    ).fetchone()
    by_verdict = {
        r["verdict"]: r["n"]
        for r in conn.execute(
            "SELECT verdict, COUNT(*) AS n FROM runs GROUP BY verdict ORDER BY n DESC"
        )
    }
    return {"runs": total, "successes": succeeded, "by_verdict": by_verdict}


def import_existing(
    conn: sqlite3.Connection, results_root: Path, *, subdir: str = "runs"
) -> int:
    """把 bench 已经跑出来的结果登记进历史（平台不该假装矩阵没跑过）。"""
    base = Path(results_root) / subdir
    if not base.exists():
        return 0
    imported = 0
    for child in sorted(base.iterdir()):
        meta_path = child / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("defense", "off")
        record_run(conn, meta, source="bench")
        imported += 1
    return imported
