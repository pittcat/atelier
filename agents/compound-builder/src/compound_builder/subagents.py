"""CompoundBuilder 的子代理清单。

按 plan KTD-7:本 Agent 走 LangGraph StateGraph 装配,不需要传统 sub_agent。
`SUBAGENTS` 留作 future extension placeholder(本阶段为 `[]`)。

详见 `nodes/` 目录的 10 个节点(coordinator / executor / validator / ...);
评测专用 reviewer 在 `dimension_reviewer.py` 中实现。
"""

from __future__ import annotations

SUBAGENTS: list[dict] = []

__all__ = ["SUBAGENTS"]
