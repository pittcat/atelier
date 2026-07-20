"""Agent 注册表。

把每个 Agent 的实例(即 langgraph 编译后的 `agent`)挂到 slug 上。

注意:Agent 目录名可能含 ``-``(e.g. ``compound-builder``),Python module
名必须 ``_``,所以本注册表用 ``AGENT_REGISTRY["..._module"]`` 提供**正确**
的 import path,而不依赖硬编码 slug-to-module 转换。
"""

from __future__ import annotations

import importlib
from typing import Any


def _try_import(slug: str) -> Any | None:
    """懒加载 Agent,避免 gateway 启动时把所有 Agent 都装载。

    从 ``AGENT_REGISTRY[slug]["module"]`` 读出 module path(由配置给出,
    避开 dash directory 命名陷阱)。
    """
    info = AGENT_REGISTRY.get(slug, {})
    module_path = info.get("module")
    if not module_path:
        return None
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, "agent")
    except Exception:
        return None


# 默认只列 slug + 描述;真正的 graph 走懒加载
# ``module`` 是固定的 Python import path(必须用下划线),不依赖 slug 自动推断。
AGENT_REGISTRY: dict[str, dict] = {
    "code-writer": {
        "slug": "code-writer",
        "display": "Code Writer",
        "description": "Atelier 主代码编写 Agent：规划 + 实现 + 测试 + commit。",
        "module": "code_writer.agent",
    },
    "compound-builder": {
        "slug": "compound-builder",
        "display": "Compound Builder",
        "description": (
            "Plan-driven multi-agent orchestrator: 10-node StateGraph with 6-dim "
            "parallel review and ship gating. Unit-by-unit TDD with explicit phase authority."
        ),
        # sys.path 中含 `agents/`,所以 compound_builder 直连(类似 code_writer)。
        "module": "compound_builder.agent",
    },
    "modem-log-analyzer": {
        "slug": "modem-log-analyzer",
        "display": "Modem Log Analyzer",
        "description": (
            "Atelier 平台下的 NuttX Modem 单轮失败日志分析 Agent。 "
            "CLI-first: analyze --evb-log <file> --output <dir>; 同步输出 report.md + analysis.json。"
        ),
        "module": "modem_log_analyzer.agent",
    },
}


def get_agent(slug: str) -> Any:
    """按 slug 拿到 Agent 实例(懒加载)。"""
    if slug not in AGENT_REGISTRY:
        raise KeyError(f"unknown agent: {slug}")
    inst = _try_import(slug)
    if inst is None:
        raise RuntimeError(f"agent '{slug}' failed to import")
    return inst
