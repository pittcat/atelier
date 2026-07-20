"""Unit 1: tools.py 必须不暴露 bash / git_commit / git_push / 通用 write_file (S16)。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _import_tools():
    from modem_log_analyzer.tools import build_tools

    return build_tools()


def test_tool_registry_exists():
    tools = _import_tools()
    assert isinstance(tools, list)


def test_no_git_push_in_tools():
    tools = _import_tools()
    names = {t.name for t in tools}
    assert "git_push" not in names
    assert "git_push_tool" not in names


def test_no_bash_in_tools():
    """bash / git_commit / 通用 write_file 都不应在主代理工具集。

    只读分析 Agent 不应能执行任意 shell。
    """
    tools = _import_tools()
    names = {t.name for t in tools}
    for forbidden in ("bash", "shell", "bash_tool", "shell_tool"):
        assert forbidden not in names, f"主代理不应暴露 {forbidden}"


def test_no_git_commit_in_tools():
    tools = _import_tools()
    names = {t.name for t in tools}
    assert "git_commit" not in names


def test_no_general_write_file_in_tools():
    tools = _import_tools()
    names = {t.name for t in tools}
    # 通用 write_file 不允许注册; 报告写文件由 CLI 负责
    assert "write_file" not in names
    assert "write_file_tool" not in names


def test_tool_count_below_5():
    """S16: subagent 工具数 ≤ 5；主代理也应保持精简。"""
    tools = _import_tools()
    assert len(tools) <= 5, f"主代理工具过多 ({len(tools)}): {[t.name for t in tools]}"
