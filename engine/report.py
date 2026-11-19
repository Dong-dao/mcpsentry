"""Report 装配：把 oracle verdict + 轨迹 + 代理证据流合成 contracts.Report。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import (
    DetectionLayer,
    Metrics,
    Report,
    ReproInfo,
    RunConfig,
    TaintEdge,
    TrajectoryStep,
    Verdict,
)


def assemble_report(
    config: RunConfig,
    engine_version: str,
    verdict: Verdict,
    trajectory: list[TrajectoryStep],
    proxy_entries: list[dict[str, Any]],
    first_payload: str,
) -> Report:
    taint_edges = [
        TaintEdge(
            source_call_id=str(p.get("source_call_id", "")),
            source_tool=str(p.get("source_tool", "")),
            sink_call_id=str(p.get("call_id", "")),
            sink_tool=str(p.get("sink_tool", "")),
            sink_field=str(p.get("sink_field", "")),
            layer=DetectionLayer(p["layer"]),
            blocked=bool(p.get("blocked")),
            matched_snippet=str(p.get("matched_snippet", "")),
        )
        for e in proxy_entries
        if e.get("method") == "edge" and (p := e.get("payload"))
    ]

    substring_hits = sum(1 for e in taint_edges if e.layer is DetectionLayer.SUBSTRING)
    semantic_calls = sum(
        1 for e in proxy_entries if e.get("method") == "verdict"
    )
    downgraded = any(e.get("method") == "downgraded" for e in proxy_entries)

    return Report(
        run_id=config.run_id,
        verdict=verdict,
        trajectory=trajectory,
        taint_edges=taint_edges,
        metrics=Metrics(
            latency_overhead_ms={},
            substring_hits=substring_hits,
            semantic_layer_calls=semantic_calls,
            downgraded=downgraded,
        ),
        repro=ReproInfo(
            seed=config.attack.seed,
            engine_version=engine_version,
            payload_hash=hashlib.sha256(first_payload.encode("utf-8")).hexdigest(),
        ),
    )


def replay_hash(report: Report) -> str:
    """回放一致性哈希（基准规格 §5/§7）：时间戳归零后的规范化 report 摘要。

    轨迹里的 tool_calls.timestamp_ms 是运行时刻值，重放必然不同，不计入一致性；
    其余字段（含确定性 call_id、payload 哈希、taint_edges 序列）必须逐字节一致。
    """
    data = report.model_dump()
    for step in data.get("trajectory", []):
        for call in step.get("tool_calls", []):
            call["timestamp_ms"] = 0
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
