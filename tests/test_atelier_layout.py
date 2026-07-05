"""Atelier 顶层测试:仅检查结构,不依赖任何第三方库。

启动:
    cd atelier && pytest -q tests/
"""

from __future__ import annotations

import re
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
    """git_push / shell_push 不能作为工具注册到 main agent。

    静态检查:不在顶层测试运行时 import tools(顶层 venv 可能没装所有
    Agent 依赖);改用 grep tools.py 源文件 + 比对 ``def git_push`` 等模式。
    """
    tools = ROOT / "agents/code-writer/src/code_writer/tools.py"
    assert tools.exists()
    txt = tools.read_text()
    # 反向断言
    for forbidden in ("git_push_tool", '"git_push"', "def git_push"):
        assert forbidden not in txt, f"tools.py 仍含禁用声明 {forbidden}"


def test_gateway_layout():
    g = ROOT / "gateway/api"
    assert g.exists()
    assert (g / "main.py").exists()
    assert (g / "routers/code_writer.py").exists()


def test_subagent_default_three():
    txt = (ROOT / "agents/code-writer/src/code_writer/subagents.py").read_text()
    for name in ("researcher", "tester", "reviewer"):
        assert f'name="{name}"' in txt


# ============================================================
# Compound Builder 接入测试(plan R21)
# ============================================================
def test_compound_builder_layout():
    cb = ROOT / "agents" / "compound-builder"
    assert cb.exists()
    assert (cb / "src/compound_builder/agent.py").exists()
    assert (cb / "src/compound_builder/graph.py").exists()
    assert (cb / "src/compound_builder/state.py").exists()
    assert (cb / "langgraph.json").exists()
    assert (cb / "Makefile").exists()

    # 10 节点(nodes/*.py)
    nodes_dir = cb / "src/compound_builder/nodes"
    for name in (
        "coordinator.py", "executor.py", "validator.py", "fixer.py",
        "review_coordinator.py", "dimension_reviewer.py",
        "review_synthesizer.py", "shipper.py", "reporter.py",
        "progress_steward.py",
    ):
        assert (nodes_dir / name).exists(), f"missing node: {name}"


def test_compound_builder_no_push_in_tools():
    """R9:git_push 类工具绝不能注册。

    静态检查 vs docstring 反向断言(后者的 `\"git_push\"` 是合法警告字符串)。
    """
    tools = ROOT / "agents/compound-builder/src/compound_builder/tools.py"
    assert tools.exists()
    txt = tools.read_text()
    # 真注册会用 @tool 包 def git_push(...),或 import 时 name="git_push"
    assert not re.search(r"@tool[\s\S]{0,200}?def\s+git_push(?:_tool)?\s*\(", txt), \
        "tools.py 含 @tool 装饰的 def git_push"
    assert not re.search(r"name\s*=\s*[\"']git_push[\"']", txt), \
        "tools.py 仍有 name='git_push' 的工具"
    # 反向断言:_assert_no_push 必须存在(本文件 self-check)
    assert "_assert_no_push" in txt, "tools.py 缺少 _assert_no_push 反向断言"


def test_compound_builder_no_push_in_static_analysis():
    """静态 grep compound-builder 源码,找出**任何** ``def git_push(...)`` 函数定义
    或 ``@tool`` 装饰的 git_push。注意:docstring 中的 ``"git_push"`` 是允许的
    (反向断言本来就会显示禁用字符串)。"""
    cb = ROOT / "agents/compound-builder/src/compound_builder"
    found = []
    for py in cb.rglob("*.py"):
        text = py.read_text()
        # 真正会注册成 LangChain 工具的代码模式
        if re.search(r"@tool[\s\S]{0,200}?def\s+git_push\b", text):
            found.append(str(py.relative_to(ROOT)))
        if re.search(r"def\s+git_push(?:_tool)?\s*\(", text):
            found.append(str(py.relative_to(ROOT)))
    assert not found, f"compound-builder 源码仍含 git_push 工具定义: {found}"


def test_compound_builder_registered_in_gateway():
    """R15:gateway registry 必须含 compound-builder。"""
    text = (ROOT / "gateway/api/registry.py").read_text()
    assert '"compound-builder"' in text
    assert "Compound Builder" in text


def test_compound_builder_routes_registered():
    """R16/R17:compound_builder_router 必须注册到 ALL_ROUTERS。"""
    init_text = (ROOT / "gateway/api/routers/__init__.py").read_text()
    assert "compound_builder_router" in init_text
    assert (ROOT / "gateway/api/routers/compound_builder.py").exists()
