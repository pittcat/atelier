"""CompoundBuilder —— Atelier 平台下的 Agent 主入口。

被 ``langgraph.json`` 引用:
    graphs: { "compound_builder": ".../agent.py:agent" }

启动:
    langgraph dev           # LangGraph Studio
    python -m compound_builder.cli run

本 Agent 走 LangGraph StateGraph 装配(plan KTD-1 / KTD-7:脱离 Deep Agents
大厨模式),10 个节点 + Send fan-out + Join,详见 ``graph.py``。
"""
from __future__ import annotations

import os
from typing import Any

from compound_builder.graph import build_graph
from compound_builder.tracing import init_tracing


def build_agent() -> Any:
    """工厂函数:构造并返回 compiled StateGraph。"""
    init_tracing(
        project=os.getenv("LANGSMITH_PROJECT", "atelier-compound_builder")
    )
    return build_graph()


# langgraph.json 入口:模块顶层 ``agent`` 固定名字
agent = build_agent()


__all__ = ["agent", "build_agent"]
