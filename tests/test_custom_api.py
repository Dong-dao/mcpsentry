"""运行时「接入自己的 MCP」契约测试。

覆盖：模板模式向后兼容、command 白名单、strict 档接受、probe 成功/失败/未启用；
真实攻击链路由既有 bench/runner 测试覆盖，本文件不重复跑 120 组矩阵。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import platform_api.app as api
import platform_api.custom as custom_api
import platform_api.history as history
from range.specs import target

ROOT = Path(__file__).resolve().parent.parent
TAINT_FIXTURE = ROOT / "tests" / "fixtures" / "taint_backend.py"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("MCPSENTRY_DB", str(tmp_path / "history.db"))
    monkeypatch.setenv("MCPSENTRY_ALLOW_CUSTOM", "1")
    with TestClient(api.app) as c:
        yield c


def _template_body(client: TestClient) -> dict:
    body = client.get("/api/custom/example").json()
    body.pop("command", None)
    return body


def test_custom_example_is_ready_to_submit(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    assert body["command"][-1] == "{workdir}"
    assert body["tool_classes"]["send_email"] == "sink"
    assert body["defense"] == "block"
    assert body["confirm"] is True


def test_custom_run_registers_target_and_queues(client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_perform(run_id: str, req, hooks=None) -> None:
        calls.append((run_id, req.target))

    monkeypatch.setattr(client.app.state.orchestrator, "perform", fake_perform)

    body = _template_body(client)
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["run_id"].startswith("c-")
    assert data["target"].startswith("C-")
    assert calls == [(data["run_id"], data["target"])]

    entry = target(data["target"])
    # 未传 command：保持 6113a0a 的内置模板执行体
    assert entry.backend_command == custom_api._backend_command(body["template"])
    assert entry.profile == body["template"]
    assert entry.is_applicable("A2_indirect_tool_result")
    assert not entry.is_applicable("A3_description_poisoning")

    queued = history.get_run(client.app.state.db, data["run_id"])
    assert queued is not None and queued["status"] == "queued"
    assert queued["note"] == body["note"]


def test_custom_with_command_uses_uploaded_backend_command(client: TestClient, monkeypatch) -> None:
    async def fake_perform(run_id: str, req, hooks=None) -> None:
        return None

    monkeypatch.setattr(client.app.state.orchestrator, "perform", fake_perform)
    body = client.get("/api/custom/example").json()
    command = [sys.executable, "-u", "-m", "range.backend", "--profile", "t1", "--workdir", "{workdir}"]
    body["command"] = command
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 202, resp.text
    entry = target(resp.json()["target"])
    assert entry.backend_command == tuple(command)
    assert entry.profile == "custom"
    assert "{workdir}" in entry.backend_command[-1]


def test_custom_accepts_strict_defense(client: TestClient, monkeypatch) -> None:
    async def fake_perform(run_id: str, req, hooks=None) -> None:
        return None

    monkeypatch.setattr(client.app.state.orchestrator, "perform", fake_perform)
    body = _template_body(client)
    body["defense"] = "strict"
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 202, resp.text
    assert resp.json()["config"]["defense"] == "strict"
    assert "-strict-" in resp.json()["run_id"]


def test_custom_rejects_unknown_template(client: TestClient) -> None:
    body = _template_body(client)
    body["template"] = "t9"
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "template" in resp.json()["detail"]


def test_custom_rejects_non_python_command(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    body["command"] = ["curl", "https://evil.example"]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "python" in resp.json()["detail"]


def test_custom_rejects_invalid_command_arg(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    body["command"] = [sys.executable, ""]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "command" in resp.json()["detail"]


def test_custom_rejects_missing_confirm(client: TestClient) -> None:
    body = client.get("/api/custom/example").json()
    body["confirm"] = False
    assert client.post("/api/custom/runs", json=body).status_code == 422


def test_custom_rejects_tool_outside_template(client: TestClient) -> None:
    body = _template_body(client)
    body["tool_classes"] = {"read_doc": "source", "evil_tool": "sink"}
    body["sinks"] = ["evil_tool"]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "工具" in resp.json()["detail"]


def test_custom_rejects_a3_and_missing_source(client: TestClient) -> None:
    body = _template_body(client)
    body["attack_class"] = "A3_description_poisoning"
    assert client.post("/api/custom/runs", json=body).status_code == 422

    body = _template_body(client)
    body["tool_classes"] = {"send_email": "sink"}
    body["sinks"] = ["send_email"]
    resp = client.post("/api/custom/runs", json=body)
    assert resp.status_code == 422
    assert "source" in resp.json()["detail"]


def test_probe_lists_tools(client: TestClient) -> None:
    command = [sys.executable, str(TAINT_FIXTURE)]
    resp = client.post("/api/custom/probe", json={"command": command, "confirm": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["duration_ms"], int) and data["duration_ms"] >= 0
    names = [tool["name"] for tool in data["tools"]]
    assert {"read_external_doc", "send_email"} <= set(names)
    assert all("description" in t and "input_schema" in t for t in data["tools"])


def test_probe_requires_confirm_and_valid_command(client: TestClient) -> None:
    command = [sys.executable, str(TAINT_FIXTURE)]
    resp = client.post("/api/custom/probe", json={"command": command})
    assert resp.status_code == 422
    assert "confirm" in resp.json()["detail"]

    resp = client.post(
        "/api/custom/probe", json={"command": ["curl", "https://evil.example"], "confirm": True}
    )
    assert resp.status_code == 422
    assert "python" in resp.json()["detail"]


def test_probe_timeout_returns_504(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(custom_api, "PROBE_TIMEOUT_SECONDS", 0.2)
    resp = client.post(
        "/api/custom/probe",
        json={"command": [sys.executable, "-c", "import time; time.sleep(10)"], "confirm": True},
    )
    assert resp.status_code == 504, resp.text
    assert "超时" in resp.json()["detail"]


def test_probe_init_failure_returns_502(client: TestClient) -> None:
    resp = client.post(
        "/api/custom/probe",
        json={"command": [sys.executable, "-c", "import sys; sys.exit(3)"], "confirm": True},
    )
    assert resp.status_code == 502, resp.text
    assert "无法初始化" in resp.json()["detail"]


def test_custom_disabled_by_default(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("MCPSENTRY_ALLOW_CUSTOM", raising=False)
    assert client.get("/api/custom/example").status_code == 403
    body = {
        "name": "x",
        "template": "t1",
        "tool_classes": {"read_doc": "source", "send_email": "sink"},
        "sinks": ["send_email"],
        "confirm": True,
    }
    assert client.post("/api/custom/runs", json=body).status_code == 403
    probe = client.post(
        "/api/custom/probe",
        json={"command": [sys.executable, str(TAINT_FIXTURE)], "confirm": True},
    )
    assert probe.status_code == 422
    assert "未启用" in probe.json()["detail"]
