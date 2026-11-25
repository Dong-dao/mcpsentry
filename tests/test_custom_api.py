"""运行时「接入自己的 MCP」契约测试。

只测接入层：配置校验、白名单、注册与排队；真实攻击链路由既有 bench/runner 测试覆盖，
本文件不重复跑 120 组矩阵。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import platform_api.app as api
import platform_api.history as history
from range.specs import target


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MCPSENTRY_DB", str(tmp_path / "history.db"))
    monkeypatch.setenv("MCPSENTRY_ALLOW_CUSTOM", "1")
    with TestClient(api.app) as c:
        yield c


def test_custom_example_is_ready_to_submit(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    assert body["command"][-1] == "{workdir}"
    assert body["tool_classes"]["send_email"] == "sink"
    assert body["confirm"] is True


def test_custom_run_registers_target_and_queues(client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_perform(run_id: str, req, hooks=None) -> None:
        calls.append((run_id, req.target))

    monkeypatch.setattr(client.app.state.orchestrator, "perform", fake_perform)

    body = client.get("/api/custom/example").json()
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["run_id"].startswith("c-")
    assert data["target"].startswith("C-")
    assert calls == [(data["run_id"], data["target"])]

    entry = target(data["target"])
    assert entry.backend_command == tuple(body["command"])
    assert entry.is_applicable("A2_indirect_tool_result")
    assert not entry.is_applicable("A3_description_poisoning")

    queued = history.get_run(client.app.state.db, data["run_id"])
    assert queued is not None and queued["status"] == "queued"
    assert queued["note"] == body["note"]


def test_custom_rejects_non_python_command(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    body["command"] = ["curl", "https://evil.example"]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "python" in resp.json()["detail"]


def test_custom_rejects_a3_and_missing_source(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    body["attack_class"] = "A3_description_poisoning"
    assert client.post("/api/custom/runs", json=body).status_code == 422

    body = client.get("/api/custom/example").json()
    body["tool_classes"] = {"send_email": "sink"}
    body["sinks"] = ["send_email"]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "source" in resp.json()["detail"]


def test_custom_disabled_by_default(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("MCPSENTRY_ALLOW_CUSTOM", raising=False)
    assert client.get("/api/custom/example").status_code == 403
    body = {
        "name": "x",
        "command": ["python", "-V"],
        "tool_classes": {"read_doc": "source", "send_email": "sink"},
        "sinks": ["send_email"],
        "confirm": True,
    }
    assert client.post("/api/custom/runs", json=body).status_code == 403
