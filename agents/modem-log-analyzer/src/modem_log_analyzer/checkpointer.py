"""ModemLogAnalyzer 的 Checkpointer 工厂。

按 AGENTS.md 第四条：
  - 本地 / 个人：MemorySaver
  - 团队 / 跨进程：PostgresSaver
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver


def build_checkpointer() -> BaseCheckpointSaver | None:
    """MemorySaver：纯本地，重启即丢。仅 dev 用。"""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
