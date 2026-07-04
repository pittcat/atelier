"""{{ cookiecutter.agent_pascal }} —— 工具 / 代理 单元测试。
"""

import pytest

from {{ cookiecutter.agent_slug }}.agent import agent
from {{ cookiecutter.agent_slug }}.subagents import SUBAGENTS


def test_agent_loads():
    """主代理能成功 import（langgraph.json 入口）。"""
    assert agent is not None
    assert hasattr(agent, "invoke")
    assert hasattr(agent, "get_state_history")
    assert hasattr(agent, "stream")


def test_subagent_registry():
    """必须包含默认三件套。"""
    names = {s["name"] for s in SUBAGENTS}
    assert {"researcher", "tester", "reviewer"}.issubset(names)
    # 深度限制：subagent 不允许再挂 subagent
    for s in SUBAGENTS:
        assert "subagents" not in s, "subagent 不能嵌套"


def test_no_git_push_in_tool_registry():
    """git_push 必须不暴露给任何 agent。"""
    from {{ cookiecutter.agent_slug }}.tools import build_tools
    tool_names = {t.name for t in build_tools()}
    assert "git_push" not in tool_names
    assert "shell_push" not in tool_names


def test_interrupt_configured():
    """危险工具必须出现在 interrupt_on 中。"""
    cfg = agent.config.get("configurable", {})
    interrupts = cfg.get("interrupt_on", {})
    # 至少要挡 bash / write_file / git_commit 三者之一
    assert len(interrupts) > 0
