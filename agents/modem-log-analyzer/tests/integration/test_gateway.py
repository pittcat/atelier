"""Unit 8 集成测试: Gateway 接入 + 鉴权 + 契约一致性。

按 Plan §5 Unit 8:
  - /agents 列出 modem-log-analyzer
  - 鉴权拒绝未授权请求
  - 授权调用 invoke / state / history 返回 JSON
  - 拒绝客户端提交任意服务器绝对路径(只接受 thread-scoped artifact-id)
  - 响应遵守 AnalysisResult 契约
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
GATEWAY_DIR = ROOT / "gateway" / "api"
GATEWAY_DIR_STR = str(GATEWAY_DIR)
SRC = ROOT / "agents" / "modem-log-analyzer" / "src"
# parents: [0]=integration, [1]=tests, [2]=modem-log-analyzer, [3]=agents, [4]=atelier
# 需要回到 atelier, 所以 parents[4]
ATELIER_ROOT = Path(__file__).resolve().parents[4]
GATEWAY_DIR = ATELIER_ROOT / "gateway" / "api"
GATEWAY_DIR_STR = str(GATEWAY_DIR)
SRC = ATELIER_ROOT / "agents" / "modem-log-analyzer" / "src"

# 把 gateway 和 modem-log-analyzer src 加进 sys.path
for p in (GATEWAY_DIR_STR, str(SRC), str(ROOT / "libs" / "common" / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(scope="module")
def client():
    """构造 TestClient, 不强制鉴权 (env 不设 GATEWAY_AUTH_TOKEN)。"""
    # 重要: 在 import gateway.api.main 之前, 确保 gateway 可以从 sys.path 找到
    import importlib

    if "gateway.api.main" in sys.modules:
        importlib.reload(sys.modules["gateway.api.main"])
    from gateway.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_client(monkeypatch_module):
    """构造需要鉴权的 TestClient。"""
    import importlib
    import os

    os.environ["GATEWAY_AUTH_TOKEN"] = "test-secret-token"
    if "gateway.api.main" in sys.modules:
        importlib.reload(sys.modules["gateway.api.main"])
    from gateway.api.main import app

    yield TestClient(app)
    os.environ.pop("GATEWAY_AUTH_TOKEN", None)


def test_list_agents_includes_modem_log_analyzer(client):
    """S15: /agents 必须包含 modem-log-analyzer。"""
    r = client.get("/agents")
    assert r.status_code == 200
    data = r.json()
    slugs = {a["slug"] for a in data["agents"]}
    assert "modem-log-analyzer" in slugs


def test_router_registered(client):
    """Router 必须注册到 ALL_ROUTERS。"""
    # 使用 openapi 找路由
    openapi = client.get("/openapi.json").json()
    paths = list(openapi.get("paths", {}).keys())
    assert any("/agents/modem-log-analyzer" in p for p in paths), (
        f"modem-log-analyzer routes not in openapi; got {paths}"
    )


def test_router_file_exists():
    """gateway/api/routers/modem_log_analyzer.py 必须存在。"""
    p = ATELIER_ROOT / "gateway" / "api" / "routers" / "modem_log_analyzer.py"
    assert p.exists()


def test_registry_has_modem_log_analyzer():
    """registry.py 必须包含 modem-log-analyzer。"""
    txt = (ATELIER_ROOT / "gateway" / "api" / "registry.py").read_text(encoding="utf-8")
    assert '"modem-log-analyzer"' in txt
    assert "modem_log_analyzer.agent" in txt


def test_auth_required_when_token_set():
    """GATEWAY_AUTH_TOKEN 设置时, 未授权请求应被拒绝。"""
    import importlib
    import os

    os.environ["GATEWAY_AUTH_TOKEN"] = "secret"
    if "gateway.api.main" in sys.modules:
        importlib.reload(sys.modules["gateway.api.main"])
    from gateway.api.main import app

    c = TestClient(app)
    # 不带 token → 401
    r = c.get("/agents")
    assert r.status_code == 401
    # 带 token → 200
    r2 = c.get("/agents", headers={"Authorization": "Bearer secret"})
    assert r2.status_code == 200
    os.environ.pop("GATEWAY_AUTH_TOKEN", None)


def test_gateway_full_path_upload_invoke_resume_report():
    """完整 Gateway 路径: upload → invoke → resume → GET /report → DELETE。"""
    import os
    import shutil

    staging = "/tmp/modem-la-gateway-test"
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    os.environ["MODEM_LOG_ANALYZER_STAGING_DIR"] = staging

    # 必须先 import, 然后 reload (env 变化后才生效)
    import gateway.api.main as gateway_main
    from fastapi.testclient import TestClient

    client = TestClient(gateway_main.app)
    thread_id = "gateway-full-path"

    evb = open(
        ATELIER_ROOT / "agents/modem-log-analyzer/tests/fixtures/reference_case_52/evb.log",
        "rb",
    ).read()
    ctrl = open(
        ATELIER_ROOT / "agents/modem-log-analyzer/tests/fixtures/reference_case_52/control.log",
        "rb",
    ).read()

    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
        files={"artifact": ("evb.log", evb, "application/octet-stream")},
    )
    assert r.status_code == 200
    evb_id = r.json()["artifact_id"]

    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs",
        json={"evb_artifact_id": evb_id, "label": "gateway-test"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["classification"] == "NO_DEVICE_ANOMALY_FOUND"
    assert r.json()["interrupt_request"] is not None

    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
        files={"artifact": ("control.log", ctrl, "application/octet-stream")},
    )
    ctrl_id = r.json()["artifact_id"]

    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs:resume",
        json={"control_artifact_id": ctrl_id, "evb_artifact_id": evb_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["classification"] == "TEST_AUTOMATION_FAILURE_CONFIRMED"

    # 路径穿越
    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs:resume",
        json={"control_artifact_id": "../../../etc/passwd"},
    )
    assert r.status_code == 400

    # report
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/report")
    assert r.status_code == 200
    assert "## 失败概览" in r.json()["report_md"]

    # state
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/state")
    assert r.status_code == 200

    # delete
    r = client.delete(f"/agents/modem-log-analyzer/threads/{thread_id}")
    assert r.status_code == 200

    # report after delete -> 404
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/report")
    assert r.status_code == 404
