"""报告导出：JSON / Markdown / 自包含 HTML 三种形态。

HTML 是给评委和作品帖的"点开就是报告"，所以不引外部 CSS/JS；也因此
所有文本必须 `html.escape`——payload 是攻击者可控字符串，这里是 XSS 的入口。
报告固定带授权声明（技术栈文档 §11 合规条）。
"""

from __future__ import annotations

import html
import json
from typing import Any

VERDICT_LABEL = {
    "exfiltration": "数据外渗成功",
    "forbidden_call": "越权调用成功",
    "poisoning_executed": "投毒描述被执行",
    "rug_pull_triggered": "描述漂移已触发",
    "attack_failed": "攻击失败",
    "n_a_negative_control": "负对照（未执行）",
}

COMPLIANCE = (
    "本报告由 MCPSentry 在自建靶场上生成：所有 sink 均为 mock（只落盘，不发真信、"
    "不出网），未对任何第三方线上服务发起测试。"
)


def _verdict(detail: dict[str, Any]) -> dict[str, Any]:
    return detail.get("verdict") or {}


def _rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "轮次": s.get("round"),
            "载荷摘要": (s.get("payload") or "")[:120].replace("\n", " "),
            "靶标回复": (s.get("target_response") or "")[:120].replace("\n", " "),
            "工具调用": "、".join(c.get("tool", "") for c in s.get("tool_calls", [])) or "—",
        }
        for s in detail.get("report", {}).get("trajectory", [])
    ]


def _edge_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "污点源": f"{e.get('source_tool')} #{str(e.get('source_call_id'))[-8:]}",
            "进入 sink": f"{e.get('sink_tool')}.{e.get('sink_field')}",
            "检出层": e.get("layer"),
            "处置": "拦截" if e.get("blocked") else "放行（仅告警）",
            "命中片段": (e.get("matched_snippet") or "")[:80].replace("\n", " "),
        }
        for e in detail.get("report", {}).get("taint_edges", [])
    ]


def summary_lines(detail: dict[str, Any]) -> list[str]:
    v = _verdict(detail)
    meta = detail.get("meta") or {}
    config = detail.get("config") or {}
    defense = (config.get("defense") or {})
    return [
        f"判定：{VERDICT_LABEL.get(v.get('type'), v.get('type'))}（{v.get('type')}）"
        f" · success={bool(v.get('success'))}",
        f"证据：{v.get('evidence') or '无'}",
        f"靶标：{config.get('target', {}).get('id')} {config.get('target', {}).get('name', '')}"
        f" · 攻击类：{(config.get('attack') or {}).get('class')}"
        f" · 防御：{'on（' + str(defense.get('policy')) + '）' if defense.get('proxy') else 'off'}",
        f"轮次：{meta.get('rounds_used', len(detail.get('report', {}).get('trajectory', [])))}"
        f" / 上限 {config.get('attack', {}).get('max_rounds')}",
        f"复现：seed={config.get('attack', {}).get('seed')}"
        f" · engine_version={config.get('engine_version')}"
        f" · replay_hash={meta.get('replay_hash', '')}",
    ]


def to_json(detail: dict[str, Any]) -> str:
    return json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True)


def to_markdown(detail: dict[str, Any]) -> str:
    v = _verdict(detail)
    lines = [
        f"# MCPSentry 运行报告 · {detail['run_id']}",
        "",
        *[f"- {line}" for line in summary_lines(detail)],
        "",
        "## 攻击轨迹",
        "",
    ]
    rows = _rows(detail)
    if rows:
        lines += ["| " + " | ".join(rows[0].keys()) + " |", "|" + "---|" * len(rows[0])]
        lines += ["| " + " | ".join(str(c) for c in r.values()) + " |" for r in rows]
    else:
        lines.append("（本轮未执行攻击，见负对照）")
    edges = _edge_rows(detail)
    lines += ["", "## 污点边", ""]
    if edges:
        lines += ["| " + " | ".join(edges[0].keys()) + " |", "|" + "---|" * len(edges[0])]
        lines += ["| " + " | ".join(str(c) for c in r.values()) + " |" for r in edges]
    else:
        lines.append("无污点边。")
    lat = detail.get("latency") or {}
    if lat:
        lines += [
            "",
            "## 延迟（旁路，不进 replay_hash）",
            "",
            f"- 防御 {lat.get('defense')}：p50 {lat.get('p50_ms')} ms / p95 {lat.get('p95_ms')} ms"
            f" / 均值 {lat.get('mean_ms')} ms（{lat.get('samples')} 次调用）",
        ]
    lines += ["", "---", "", COMPLIANCE, ""]
    return "\n".join(lines)


_CSS = """
body{font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;
background:#0f1115;color:#e6e8ee}
main{max-width:960px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;color:#9fb3d1;
letter-spacing:.04em}
.sub{color:#8b93a7;font-size:13px;margin-bottom:20px}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;
font-weight:600;margin-right:6px}
.bad{background:#4a1520;color:#ffb4c0}.good{background:#123a24;color:#83e6ae}
.warn{background:#3c2d10;color:#ffd68a}.info{background:#1b2740;color:#a9c6ff}
ul{margin:0;padding-left:18px;color:#c8cede}li{margin:3px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border-bottom:1px solid #262b36;padding:8px 10px;text-align:left;
vertical-align:top;word-break:break-word}
th{color:#8b93a7;font-weight:600;background:#151922}
code{background:#1a1f2b;padding:1px 5px;border-radius:4px;font-size:12px}
.note{margin-top:32px;padding:14px 16px;background:#151922;border-left:3px solid #3d6cff;
color:#9aa4b8;font-size:13px}
"""

_TONE = {
    "exfiltration": "bad",
    "forbidden_call": "bad",
    "poisoning_executed": "bad",
    "rug_pull_triggered": "bad",
    "attack_failed": "good",
    "n_a_negative_control": "info",
}


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='sub'>（无记录）</p>"
    head = "".join(f"<th>{html.escape(k)}</th>" for k in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r.values()) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def to_html(detail: dict[str, Any]) -> str:
    v = _verdict(detail)
    tone = _TONE.get(v.get("type"), "warn")
    bullets = "".join(f"<li>{html.escape(s)}</li>" for s in summary_lines(detail))
    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>MCPSentry {html.escape(detail['run_id'])}</title>",
        f"<style>{_CSS}</style></head><body><main>",
        f"<h1>MCPSentry 运行报告 <span class='badge {tone}'>{html.escape(str(v.get('type')))}</span>"
        f"<span class='badge {'bad' if v.get('success') else 'good'}'>"
        f"{'攻击成功' if v.get('success') else '攻击未成功'}</span></h1>",
        f"<div class='sub'>{html.escape(detail['run_id'])}</div>",
        f"<ul>{bullets}</ul>",
        "<h2>攻击轨迹</h2>",
        _table(_rows(detail)),
        "<h2>污点边</h2>",
        _table(_edge_rows(detail)),
        "<h2>载荷原文</h2>",
    ]
    for step in detail.get("report", {}).get("trajectory", []):
        parts.append(
            f"<p class='sub'>round {step.get('round')}</p>"
            f"<pre><code>{html.escape(step.get('payload') or '')}</code></pre>"
        )
    parts += [f"<div class='note'>{html.escape(COMPLIANCE)}</div>", "</main></body></html>"]
    return "".join(parts)


FORMATS = {"json": to_json, "md": to_markdown, "html": to_html}
CONTENT_TYPE = {
    "json": "application/json; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
}


def render(detail: dict[str, Any], fmt: str) -> str:
    try:
        return FORMATS[fmt](detail)
    except KeyError:
        raise ValueError(f"unknown export format {fmt!r}; {sorted(FORMATS)}") from None
