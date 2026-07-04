"""{{ cookiecutter.agent_pascal }} —— Atelier 平台下的 Agent 主入口。

被 `langgraph.json` 引用：
  graphs: { "{{ cookiecutter.agent_slug }}": ".../agent.py:agent" }

启动方式：
    langgraph dev           # LangGraph Studio (http://localhost:2024)
    python -m {{ cookiecutter.agent_slug }}.cli run "一段话"
"""

from __future__ import annotations

import os

from deepagents import create_deep_agent
from langchain.agents.middleware import SkillsMiddleware

from {{ cookiecutter.agent_slug }}.subagents import SUBAGENTS
from {{ cookiecutter.agent_slug }}.tools import build_tools
from {{ cookiecutter.agent_slug }}.prompts import SYSTEM_PROMPT
from {{ cookiecutter.agent_slug }}.llm import get_llm
from {{ cookiecutter.agent_slug }}.checkpointer import build_checkpointer
from {{ cookiecutter.agent_slug }}.skills_loader import all_skill_sources, to_deepagents_source
from {{ cookiecutter.agent_slug }}.tracing import init_tracing


# ---- 启动期 ----
init_tracing(project=os.getenv("LANGSMITH_PROJECT", "atelier-{{ cookiecutter.agent_slug }}"))


def _build_skills_middleware() -> SkillsMiddleware | None:
    """装配 SkillsMiddleware。返回 None 表示不开 skills。"""
    sources = all_skill_sources()
    if not sources:
        return None
    deep_sources = [to_deepagents_source(s) for s in sources]
    try:
        return SkillsMiddleware(sources=deep_sources)
    except TypeError:
        # 兼容老版 deepagents
        return SkillsMiddleware(skills=deep_sources)


def build_agent():
    """工厂函数：构造并返回编译好的 LangGraph 图。"""
    llm_main = get_llm(os.getenv("ATELIER_DEFAULT_MODEL", "{{ cookiecutter.model_default }}"))
    tools = build_tools()
    checkpointer = build_checkpointer()

    middleware = []
    sm = _build_skills_middleware()
    if sm is not None:
        middleware.append(sm)

    agent = create_deep_agent(
        name="{{ cookiecutter.agent_slug }}",
        model=llm_main,
        tools=tools,
        subagents=SUBAGENTS,
        system_prompt=SYSTEM_PROMPT,
        interrupt_on={% if cookiecutter.enable_interrupt == "yes" %}{"bash": True, "write_file": True, "edit_file": True, "git_commit": True}{% else %}{}{% endif %},
        checkpointer=checkpointer,
        middleware=middleware,
    )
    return agent


# langgraph.json 入口：模块顶层的 ``agent`` 名字固定。
agent = build_agent()
