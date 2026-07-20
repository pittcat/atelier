"""ModemLogAnalyzer —— Atelier 平台下的 NuttX Modem 失败日志分析 Agent。

主入口（被 langgraph.json 引用）:
  graphs: { "modem_log_analyzer": ".../agent.py:agent" }

启动方式:
    cd agents/modem-log-analyzer
    uv sync
    cp .env.example .env  # 填好 ANTHROPIC_API_KEY / LANGSMITH_API_KEY
    make dev              # LangGraph Studio: http://localhost:2024

CLI 主入口（计划首要交付入口）:
    modem-log-analyzer analyze --evb-log <file> --output <dir>

设计要点:
  - 只读日志分析 Agent,不暴露 bash / git_commit / git_push / 通用 write_file。
  - 生产 Postgres 配置缺失必须显式失败,不能静默降级到 MemorySaver。
  - prompt 改动必须同步 docs/PROMPT.md 变更记录。
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path
from typing import Any

# 兼容 langgraph-api 的加载方式:把 src/ 加入 sys.path
_HERE = Path(__file__).resolve().parent  # src/modem_log_analyzer/
_SRC = _HERE.parent  # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _try_import_deepagents():
    """选择 factory：装上 deepagents 用 create_deep_agent；否则退回 create_react_agent。"""
    try:
        mod = importlib.import_module("deepagents")
        return mod.create_deep_agent
    except ImportError:
        warnings.warn(
            "deepagents not installed; falling back to langgraph.prebuilt.create_react_agent.",
            stacklevel=2,
        )
        from langgraph.prebuilt import create_react_agent

        return create_react_agent


def _resolve_checkpointer():
    """Checkpointer: 本地 MemorySaver, 生产 PostgresSaver 强制。

    规则:
      - 如果 LANGSMITH_LANGGRAPH_API_VARIANT 设置了, langgraph-api 会接管持久化, 返回 None。
      - 否则按 env: 有 ATELIER_CHECKPOINTER_URL → PostgresSaver; 无 → MemorySaver。
      - 注意: 本 Agent 严格要求"checkpointer 必开",所以不会返回 None (除 LangGraph API 进程)。
    """
    if os.getenv("LANGSMITH_LANGGRAPH_API_VARIANT"):
        return None

    url = os.getenv("ATELIER_CHECKPOINTER_URL")
    if url:
        from langgraph.checkpoint.postgres import PostgresSaver

        return PostgresSaver.from_conn_string(url)

    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def _try_import_skills_middleware():
    try:
        from langchain.agents.middleware import SkillsMiddleware

        return SkillsMiddleware
    except Exception:
        try:
            from deepagents.middleware import SkillsMiddleware  # type: ignore

            return SkillsMiddleware
        except Exception:
            return None


def build_agent() -> Any:
    """工厂函数：构造并返回编译好的 LangGraph 图。

    Unit 1 阶段: 骨架成立;子代理(subagents) 与 tools 在后续 Unit 接入。
    """
    from modem_log_analyzer.interrupts import INTERRUPT_MAP
    from modem_log_analyzer.llm import get_llm
    from modem_log_analyzer.prompts import SYSTEM_PROMPT
    from modem_log_analyzer.skills_loader import all_skill_sources, to_deepagents_source
    from modem_log_analyzer.subagents import SUBAGENTS
    from modem_log_analyzer.tools import build_tools
    from modem_log_analyzer.tracing import init_tracing

    init_tracing(project=os.getenv("LANGSMITH_PROJECT", "atelier-modem-log-analyzer"))

    main_model = get_llm(os.getenv("ATELIER_DEFAULT_MODEL", "claude-opus-4-8"))
    create = _try_import_deepagents()
    SkillsMiddleware = _try_import_skills_middleware()

    middleware = []
    if SkillsMiddleware is not None:
        sources = []
        for s in all_skill_sources():
            try:
                sources.append(to_deepagents_source(s))
            except Exception:
                pass
        if sources:
            try:
                middleware.append(SkillsMiddleware(sources=sources))
            except TypeError:
                try:
                    middleware.append(SkillsMiddleware(skills=sources))
                except Exception:
                    middleware = []

    agent = create(
        name="modem-log-analyzer",
        model=main_model,
        tools=build_tools(),
        subagents=SUBAGENTS,
        system_prompt=SYSTEM_PROMPT,
        interrupt_on=INTERRUPT_MAP,
        checkpointer=_resolve_checkpointer(),
        middleware=middleware,
    )
    return agent


def _build_minimal_fallback_graph() -> Any:
    """当真实 build_agent() 失败时,返回最小 LangGraph 图,让 ``langgraph dev`` 启动。

    不调用任何 LLM;只要返回的对象是 Pregel(已编译)即可。
    """
    try:
        from langgraph.graph import START, StateGraph
    except ImportError as e:
        raise RuntimeError("langgraph not installed; cannot build fallback graph") from e

    from typing_extensions import TypedDict

    class _S(TypedDict):
        messages: list

    def _noop(state: _S) -> dict:
        return {"messages": list(state.get("messages", []))}

    g = StateGraph(_S)
    g.add_node("echo", _noop)
    g.add_edge(START, "echo")
    return g.compile()


# langgraph.json 入口: 模块顶层的 ``agent`` 名字固定。
agent: Any
try:
    agent = build_agent()
except Exception as _build_err:  # noqa: BLE001
    warnings.warn(
        f"[modem_log_analyzer.agent] build_agent() failed: {_build_err!r}; "
        f"using minimal fallback graph. Set ANTHROPIC_API_KEY etc. in .env for full agent.",
        stacklevel=1,
    )
    agent = _build_minimal_fallback_graph()
