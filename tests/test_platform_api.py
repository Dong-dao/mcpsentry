"""platform_api 的端到端契约测试（成员 B）。

测的是"前端能不能靠这些接口活"，不是引擎对不对：health/targets/metrics/runs/
detail/export 的字段与状态码，外加一次真实 POST /api/runs（后台任务在
TestClient 里同步跑完，所以断言能直接看到落盘产物）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import platform_api.app as api
import platform_api.history as history


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MCPSENTRY_DB", str(tmp_path / "history.db"))
    with TestClient(api.app) as c:
        yield c


def test_health_reports_artifacts(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["runs_present"] is True
    assert "runs" in body["history"]


def test_targets_expose_applicable_and_na_cells(client: TestClient) -> None:
    body = client.get("/api/targets").json()
    assert body["matrix"] == {"total": 120, "applicable": 66, "negative_control": 54}
    by_id = {t["id"]: t for t in body["targets"]}
    assert by_id["T3"]["applicable"] == ["A3_description_poisoning"]
    assert set(by_id["T1"]["na"]) == {"A3_description_poisoning"}


def test_metrics_is_the_bundled_summary(client: TestClient) -> None:
    body = client.get("/api/metrics").json()
    bundled = json.loads((Path("bench/metrics/summary.json")).read_text(encoding="utf-8"))
    assert body["counts"] == bundled["counts"]
    assert body["canonical"]["replay_consistency"] == bundled["canonical"]["replay_consistency"]


def test_run_detail_carries_graph_and_repro(client: TestClient) -> None:
    runs = client.get("/api/runs", params={"limit": 5}).json()["items"]
    assert runs, "历史里应至少有 bench 导入的运行"
    detail = client.get(f"/api/runs/{runs[0]['run_id']}").json()
    assert detail["graph"]["nodes"], "污点图至少要有攻击者与靶标节点"
    assert detail["report"]["repro"]["engine_version"]
    assert {"attacker", "agent"} <= {n["kind"].split(":")[0] for n in detail["graph"]["nodes"]}
    edges = detail["graph"]["edges"]
    assert len({e["id"] for e in edges}) == len(edges), "边 id 必须唯一：前端拿它做 React key"
    assert detail["remediation"], "报告必须带修复建议（项目书 §二 的交付项）"


def test_missing_run_is_404_not_empty_200(client: TestClient) -> None:
    assert client.get("/api/runs/r-NOPE-A1-s42-off").status_code == 404
    assert client.get("/api/runs/r-NOPE-A1-s42-off/export", params={"format": "md"}).status_code == 404


def test_export_formats(client: TestClient) -> None:
    run_id = client.get("/api/runs", params={"limit": 1}).json()["items"][0]["run_id"]
    md = client.get(f"/api/runs/{run_id}/export", params={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert "MCPSentry 运行报告" in md.text
    assert "## 修复建议" in md.text
    # config.json 里攻击类是 class_，导出取错键会安静地渲染成 None
    assert "攻击类：A" in md.text and "攻击类：None" not in md.text
    html = client.get(f"/api/runs/{run_id}/export", params={"format": "html"}).text
    assert "<!doctype html>" in html[:40].lower()
    assert "修复建议" in html
    assert client.get(f"/api/runs/{run_id}/export", params={"format": "exe"}).status_code == 422


def test_post_run_executes_and_records_history(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(
        "/api/runs",
        json={"target": "T1", "attack_class": "A1_direct_injection", "seed": 42, "defense": "off"},
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    assert run_id.startswith("p-T1-A1-s42-off-")
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["subdir"] == "platform"
    assert detail["verdict"]["type"] in {"forbidden_call", "attack_failed"}
    row = client.get(f"/api/runs/{run_id}").json()["history"]
    assert row["status"] == "done"


def test_post_run_rejects_unknown_cell(client: TestClient) -> None:
    bad = client.post("/api/runs", json={"target": "T9", "attack_class": "A1_direct_injection"})
    assert bad.status_code == 422
    unknown = client.post("/api/runs", json={"target": "T1", "attack_class": "A9_nonsense"})
    assert unknown.status_code == 422


def test_matrix_batch_requires_confirm(client: TestClient) -> None:
    assert client.post("/api/matrix", json={"targets": ["T1"]}).status_code == 400
    ok = client.post(
        "/api/matrix",
        json={"targets": ["T1"], "classes": ["A1_direct_injection"], "seeds": [42],
              "tiers": ["off"], "confirm": True},
    )
    assert ok.status_code == 202
    assert ok.json()["cells"] == 1


def test_demo_preset_is_readable_without_running(client: TestClient) -> None:
    bundle = client.get("/api/demo/preset")
    assert bundle.status_code == 200, "预置 demo 缺失时前端第一屏会空"
    body = bundle.json()
    assert [r["defense"] for r in body["runs"]] == ["off", "block"]
    assert body["runs"][0]["verdict"]["success"] is True
    assert body["runs"][1]["verdict"]["success"] is False


def test_remediation_distinguishes_refusal_from_blocking(client: TestClient) -> None:
    """T5 的提示词加固让攻击自然失败：代理没拦任何东西时不能写"拦下了 0 条"。"""
    detail = client.get("/api/runs/r-T5-A1_direct_injection-s42-block").json()
    assert detail["verdict"]["type"] == "attack_failed"
    assert detail["report"]["taint_edges"] == []
    text = " ".join(detail["remediation"])
    assert "一条都没拦" in text and "拦下了 0 条" not in text


def test_history_import_is_idempotent(client: TestClient, tmp_path: Path) -> None:
    conn = history.connect(tmp_path / "again.db")
    first = history.import_existing(conn, api.RESULTS_ROOT)
    second = history.import_existing(conn, api.RESULTS_ROOT)
    assert first == second and first > 0
    assert history.stats(conn)["runs"] == first


def test_export_html_escapes_attacker_payload() -> None:
    """payload 是攻击者可控字符串，导出 HTML 不转义就是存储型 XSS。"""
    evil = "<script>alert(1)</script>"
    detail = {
        "run_id": "x",
        "verdict": {"type": "attack_failed", "success": False, "evidence": evil},
        "config": {
            "target": {"id": "T1", "name": "客服"},
            "attack": {"class": "A1", "seed": 1, "max_rounds": 6},
            "defense": {"proxy": False},
        },
        "meta": {},
        "report": {
            "trajectory": [{"round": 1, "payload": evil, "target_response": evil, "tool_calls": []}],
            "taint_edges": [],
        },
        "latency": {},
    }
    page = api.export.to_html(detail)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
