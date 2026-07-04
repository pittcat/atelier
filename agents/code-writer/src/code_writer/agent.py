"""Code Writer Agent —— Atelier 平台下的代码编写 Agent。

主代理：
  - claude-opus-4-8
  - 子代理：researcher / tester / reviewer
  - 工具：read_file / write_file / edit_file / bash(受限) / git_status/diff/commit

Skills：
  - SkillsMiddleware 加载本地 ./skills/（按需注入 SKILL.md）

MCP：
  - 默认不挂 MCP server；可由 .env 中的
        ATELIER_MCP_GITHUB=1
        ATELIER_MCP_DOCS=1
    开启。

（按 AGENTS.md 规则 #8：只加载项目级 skill 与 MCP，不读取 ~/.claude/skills
等用户级 / 全局级配置。）

启动：
    cd agents/code-writer
    uv sync
    cp .env.example .env && 编辑之
    langgraph dev            # LangGraph Studio: http://localhost:2024
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path
from typing import Any

# 兼容 langgraph-api 的加载方式:它通过 spec_from_file_location 直接 exec_module 加载
# 本文件,把 cwd 加进 sys.modules,但不会自动把 src/ 加进 sys.path。
# 这里手动加,保证 `from code_writer.subagents import ...` 在 langgraph-api venv 里也能解析。
_HERE = Path(__file__).resolve().parent          # src/code_writer/
_SRC = _HERE.parent                              # src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _try_import_deepagents():
    """选择 factory：装上 deepagents 用 create_deep_agent；否则退回 create_react_agent。

    退化路径保留是因为历史版本（深 agents 在 PyPI 不可达期间）也能跑通基础 langgraph studio。
    """
    try:
        mod = importlib.import_module("deepagents")
        return getattr(mod, "create_deep_agent")
    except ImportError:
        warnings.warn(
            "deepagents not installed; falling back to langgraph.prebuilt.create_react_agent. "
            "Subagent / skills / persistent-filesystem middleware will be reduced.",
            stacklevel=2,
        )
        from langgraph.prebuilt import create_react_agent
        return create_react_agent


def _build_checkpointer():
    url = os.getenv("ATELIER_CHECKPOINTER_URL")
    if url:
        from langgraph.checkpoint.postgres import PostgresSaver
        return PostgresSaver.from_conn_string(url)
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


def _try_import_skills_middleware():
    """SkillsMiddleware 在 langchain.agents.middleware.langchain 上。

    旧版 deepagents 也提供 SkillsMiddleware；二者有一个即可。
    """
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
    """工厂函数。返回 LangGraph 图（main agent）。"""
    from code_writer.subagents import SUBAGENTS
    from code_writer.tools import build_tools
    from code_writer.prompts import SYSTEM_PROMPT
    from code_writer.llm import get_llm
    from code_writer.interrupts import INTERRUPT_MAP
    from code_writer.tracing import init_tracing
    from code_writer.skills_loader import all_skill_sources, to_deepagents_source

    init_tracing(project=os.getenv("LANGSMITH_PROJECT", "atelier-code-writer"))

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
        name="code-writer",
        model=main_model,
        tools=build_tools(),
        subagents=SUBAGENTS,
        system_prompt=SYSTEM_PROMPT,
        interrupt_on=INTERRUPT_MAP,
        checkpointer=_resolve_checkpointer(),
        middleware=middleware,
    )
    return agent


def _resolve_checkpointer():
    """返回 checkpointer。

    在 LangGraph API 进程内(`LANGSMITH_LANGGRAPH_API_VARIANT=local_dev` 或 `licensed`),
    持久化由平台接管,不允许用户在 graph 上挂 checkpointer(否则 dev 启动会 hard fail)。
    直跑 (`python -m code_writer.cli`) 时,我们用 MemorySaver / PostgresSaver。
    """
    if os.getenv("LANGSMITH_LANGGRAPH_API_VARIANT"):  # 在 langgraph-api 进程内
        return None
    return _build_checkpointer()


def _build_minimal_fallback_graph() -> Any:
    """当真实 build_agent() 失败(网络、LLM key 缺失、依赖过时等)时,
    返回一个最小 LangGraph 图,让 `langgraph dev` 至少能启动并暴露
    /threads /runs /docs 端点 —— 不调用任何 LLM。

    对 langgraph-api 来说,只要返回的对象是 Pregel(已编译)即可。
    """
    try:
        from langgraph.graph import START, StateGraph
    except ImportError as e:
        raise RuntimeError("langgraph not installed; cannot build fallback graph") from e

    from typing_extensions import TypedDict

    class _S(TypedDict):
        messages: list

    def _noop(state: _S) -> dict:
        # 不调用 LLM,直接 echo 现有消息
        return {"messages": list(state.get("messages", []))}

    g = StateGraph(_S)
    g.add_node("echo", _noop)
    g.add_edge(START, "echo")
    # 不设 checkpointer —— 由 LangGraph API 在部署时注入(参见 langgraph_api/graph.py 的 heads-up 警告)
    return g.compile()


# ---- 顶层:立即构造(供 langgraph.json 直接 import)----
agent: Any
try:
    agent = build_agent()
except Exception as _build_err:  # noqa: BLE001
    warnings.warn(
        f"[code_writer.agent] build_agent() failed: {_build_err!r}; "
        f"using minimal fallback graph. Set ANTHROPIC_API_KEY etc. in .env for full agent.",
        stacklevel=1,
    )
    agent = _build_minimal_fallback_graph()
