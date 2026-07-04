"""Code Writer Agent 的 State。

默认继承 LangGraph 的 MessagesState。暂不扩展字段。
"""

from __future__ import annotations

from langgraph.graph import MessagesState


class CodeWriterState(MessagesState):
    """扩展点：可加入 plan_steps / last_review_verdict 等。"""
    pass
