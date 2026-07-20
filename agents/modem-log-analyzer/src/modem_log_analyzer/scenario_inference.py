"""ModemLogAnalyzer —— 测试场景推断 (Unit 4)。

按 Plan §1 R4 + §5 Unit 4:
  - 没有用户描述时, Agent 必须根据命令序列和板端事件推断场景。
  - 推断必须给出 confidence (low/medium/high)。
  - 混合场景应保持子流程边界(通话中短信/ping)。
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def infer_scenario(events: list[dict]) -> dict[str, Any] | None:
    """根据事件流推断测试场景与置信度。

    返回 ``{name: str, confidence: low|medium|high, business_actions: list}``。
    若无任何业务命令 → 返回 ``{name: "未知场景", confidence: "low", ...}``。
    """
    cmd_events = [ev for ev in events if ev.get("kind") == "command"]
    if not cmd_events:
        return {
            "name": "未知场景",
            "confidence": "low",
            "business_actions": [],
            "rationale": "no business commands found in events",
        }

    actions = [ev.get("business_action") for ev in cmd_events]
    counter = Counter(a for a in actions if a)
    # 排除 session_entry
    counter.pop("session_entry", None)

    if not counter:
        return {
            "name": "未知场景",
            "confidence": "low",
            "business_actions": [],
            "rationale": "no recognized business actions",
        }

    # 单一动作 → 单一场景
    distinct = {a for a in counter if a and a != "unknown"}
    unknown_count = counter.get("unknown", 0)

    if len(distinct) == 1 and unknown_count == 0:
        only = next(iter(distinct))
        return {
            "name": _scenario_name_for_action(only),
            "confidence": "high",
            "business_actions": sorted(distinct),
            "rationale": f"only business action found: {only}",
        }

    # 多种业务动作 → 混合场景
    if len(distinct) >= 2:
        # 通话期间短信/ping → 主流程 call
        primary = "call" if "call" in distinct else (next(iter(distinct)) if distinct else None)
        return {
            "name": f"混合场景: {primary} + {'/'.join(sorted(distinct - {primary}))}",
            "confidence": "medium",
            "business_actions": sorted(distinct),
            "rationale": f"mixed business actions: {sorted(distinct)}",
        }

    # 大量 unknown → 置信度低
    if unknown_count > len(cmd_events) / 2:
        return {
            "name": "未知场景",
            "confidence": "low",
            "business_actions": sorted(counter.keys()),
            "rationale": f"too many unknown commands ({unknown_count}/{len(cmd_events)})",
        }

    # 兜底
    return {
        "name": _scenario_name_for_action(next(iter(distinct))) if distinct else "未知场景",
        "confidence": "medium",
        "business_actions": sorted(distinct | {"unknown"}),
        "rationale": "fallback",
    }


def _scenario_name_for_action(action: str) -> str:
    """业务动作 → 中文场景名。"""
    return {
        "call": "语音通话 (Call)",
        "sms": "短信 (SMS)",
        "data_ping": "数据/Ping (Data/Ping)",
        "setting": "状态/接口设置 (Setting)",
        "rpc_dispatch": "RPC 调度 (rpc_dispatch)",
        "session_entry": "会话入口 (session_entry)",
    }.get(action, action)


__all__ = ["infer_scenario"]
