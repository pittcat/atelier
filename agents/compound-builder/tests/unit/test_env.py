"""env —— CLI .env 解析单元测试。"""
from __future__ import annotations

from compound_builder import env


def test_resolve_dotenv_prefers_agent_local(tmp_path, monkeypatch):
    agent_dir = tmp_path / "compound-builder"
    agent_dir.mkdir()
    env_file = agent_dir / ".env"
    env_file.write_text("ATELIER_DEFAULT_MODEL=test-model\n")

    monkeypatch.setattr(env, "_AGENT_PARENT", agent_dir)
    monkeypatch.delenv("ATELIER_HOME", raising=False)

    got = env.resolve_dotenv_path()
    assert got == env_file


def test_load_cli_env_sets_variables(tmp_path, monkeypatch):
    agent_dir = tmp_path / "compound-builder"
    agent_dir.mkdir()
    (agent_dir / ".env").write_text("ATELIER_DEFAULT_MODEL=from-dotenv\n")
    monkeypatch.setattr(env, "_AGENT_PARENT", agent_dir)
    monkeypatch.delenv("ATELIER_HOME", raising=False)
    monkeypatch.delenv("ATELIER_DEFAULT_MODEL", raising=False)

    path = env.load_cli_env(override=True)
    assert path is not None
    import os
    assert os.environ.get("ATELIER_DEFAULT_MODEL") == "from-dotenv"
