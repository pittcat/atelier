"""{{ cookiecutter.agent_pascal }} 的 State Schema。

默认情况下 Deep Agents / LangGraph 的内置 state 已经够用。
仅在该 Agent 需要扩展状态时再声明。
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class {{ cookiecutter.agent_pascal }}State(MessagesState):
    """继承 LangGraph 内置 MessagesState，按需扩展字段。

    示例：
        plan_steps: list[str] = Field(default_factory=list)
        last_review_verdict: Optional[str] = None
    """
    pass


def build_state() -> type[BaseModel]:
    """返回运行时使用的 state class。
    留作扩展点。
    """
    return {{ cookiecutter.agent_pascal }}State
