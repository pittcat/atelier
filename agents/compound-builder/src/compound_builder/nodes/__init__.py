"""CompoundBuilder —— 节点共享基类与 SSOT 工具。"""
from __future__ import annotations

from typing import Any, Callable

from compound_builder.state import CompoundBuilderState


def delta(**kwargs: Any) -> dict:
    """封装一个节点返回的 delta 字典,统一语义。"""
    return dict(kwargs)


def current_unit(state: CompoundBuilderState) -> dict:
    units = state.get("units") or []
    fix_units = state.get("fix_units") or []
    if state.get("phase") == "fix_units" and fix_units:
        idx = state.get("current_unit_index", 0)
        if 0 <= idx < len(fix_units):
            return fix_units[idx]
    if units:
        idx = min(state.get("current_unit_index", 0), len(units) - 1)
        return units[idx]
    return {}


def log_event(event: str, **payload: Any) -> dict:
    """构造一个 event 节点 entry,统一进 ``results_log``。"""
    return {"event": event, **payload}


NodeFn = Callable[[CompoundBuilderState], dict[str, Any]]
