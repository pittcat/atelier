"""Agent 注册表。

把每个 Agent 的实例（即 langgraph 编译后的 `agent`）挂到 slug 上。
"""

from __future__ import annotations

from typing import Any


def _try_import(slug: str) -> Any | None:
    """懒加载 Agent，避免 gateway 启动时把所有 Agent 都装载。"""
    try:
        mod = __import__(f"agents.{slug}.src.{slug.replace('-', '_')}.agent", fromlist=["agent"])
        return getattr(mod, "agent")
    except Exception:
        return None


# 默认只列 slug + 描述；真正的 graph 走懒加载
AGENT_REGISTRY: dict[str, dict] = {
    "code-writer": {
        "slug": "code-writer",
        "display": "Code Writer",
        "description": "Atelier 主代码编写 Agent：规划 + 实现 + 测试 + commit。",
        "module": "agents.code_writer.src.code_writer.agent:agent",
    },
}


def get_agent(slug: str) -> Any:
    """按 slug 拿到 Agent 实例（懒加载）。"""
    if slug not in AGENT_REGISTRY:
        raise KeyError(f"unknown agent: {slug}")
    inst = _try_import(slug)
    if inst is None:
        raise RuntimeError(f"agent '{slug}' failed to import")
    return inst
