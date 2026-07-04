"""Gateway 鉴权 / 注册表测试。"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_health_open():
    from main import app
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert "code-writer" in r.json()["agents_loaded"]


def test_list_agents_requires_token():
    os.environ["GATEWAY_AUTH_TOKEN"] = "secret"
    from main import app
    c = TestClient(app)

    r = c.get("/agents")
    assert r.status_code == 401

    r = c.get("/agents", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401

    r = c.get("/agents", headers={"Authorization": "Bearer secret"})
    # 200 / 503 取决于是否真的 import 了 code-writer；至少不应 401
    assert r.status_code != 401
