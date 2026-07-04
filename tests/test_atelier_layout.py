"""Atelier 顶层测试：仅检查结构，不依赖任何第三方库。

启动：
    cd atelier && pytest -q tests/
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_root_files_exist():
    for f in (
        "README.md", "AGENTS.md", "CLAUDE.md", "Makefile",
        "pyproject.toml", ".gitignore", ".env.example",
        "scripts/smoke.sh",
    ):
        assert (ROOT / f).exists(), f"missing root file: {f}"


def test_template_dir_exists():
    tdir = ROOT / "_templates" / "agent-template"
    assert tdir.exists()
    assert (tdir / "cookiecutter.json").exists()


def test_example_agent_exists():
    cwd = ROOT / "agents" / "code-writer"
    assert cwd.exists()
    assert (cwd / "src/code_writer/agent.py").exists()
    assert (cwd / "langgraph.json").exists()
    assert (cwd / "Makefile").exists()


def test_example_agent_no_push_in_tools():
    """git_push / shell_push 不能作为工具注册到 main agent。"""
    import sys
    sys.path.insert(0, str(ROOT / "agents/code-writer/src"))
    from code_writer.tools import build_tools
    registered = {t.name for t in build_tools()}
    for forbidden in ("git_push", "shell_push", "git_push_tool"):
        assert forbidden not in registered, f"{forbidden} must not be a registered tool"


def test_gateway_layout():
    g = ROOT / "gateway/api"
    assert g.exists()
    assert (g / "main.py").exists()
    assert (g / "routers/code_writer.py").exists()


def test_subagent_default_three():
    txt = (ROOT / "agents/code-writer/src/code_writer/subagents.py").read_text()
    for name in ("researcher", "tester", "reviewer"):
        assert f'name="{name}"' in txt
