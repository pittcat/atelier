"""react_agent —— LangGraph 1.x 兼容工厂。"""
from __future__ import annotations

from compound_builder.react_agent import build_react_agent
from compound_builder.tools import build_tools


def test_build_react_agent_compiles():
    from compound_builder.llm import get_llm

    tools = [t for t in build_tools() if t.name == "read_file"]
    agent = build_react_agent(get_llm(), tools, prompt="test agent")
    assert agent is not None
    assert hasattr(agent, "invoke")
