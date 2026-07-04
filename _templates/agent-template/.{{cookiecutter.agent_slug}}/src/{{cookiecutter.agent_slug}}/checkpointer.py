"""{{ cookiecutter.agent_pascal }} 的 Checkpointer 工厂。

按 AGENTS.md 第四条：
  - 本地 / 个人：MemorySaver
  - 团队 / 跨进程：PostgresSaver
"""

from __future__ import annotations

import os

from langgraph.checkpoint.base import BaseCheckpointSaver


def build_checkpointer() -> BaseCheckpointSaver | None:
    {% if cookiecutter.checkpointer_kind == "memory" -%}
    """MemorySaver：纯本地，重启即丢。仅 dev 用。"""
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()
    {% else -%}
    """PostgresSaver：生产 / 团队用。"""
    from langgraph.checkpoint.postgres import PostgresSaver
    url = os.getenv("ATELIER_CHECKPOINTER_URL")
    if not url:
        raise RuntimeError(
            "Set ATELIER_CHECKPOINTER_URL=postgresql://user:pass@host/db"
        )
    return PostgresSaver.from_conn_string(url)
    {% endif %}
