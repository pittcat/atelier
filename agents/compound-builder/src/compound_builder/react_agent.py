"""ReAct Agent 工厂 —— 兼容 LangGraph 1.x API。

``create_react_agent(..., handle_tool_errors=True)`` 在新版已移除;
工具错误通过 ``ToolNode(..., handle_tool_errors=True)`` 吞掉并回传给 LLM。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_react_agent(
    model: Any,
    tools: Sequence[Any],
    *,
    prompt: str,
):
    """构造带 tool-error 容错的 ReAct Agent。"""
    from langgraph.prebuilt import ToolNode, create_react_agent

    tool_node = ToolNode(list(tools), handle_tool_errors=True)
    return create_react_agent(model, tool_node, prompt=prompt)


__all__ = ["build_react_agent"]
