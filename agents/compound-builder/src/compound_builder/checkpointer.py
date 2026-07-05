"""CompoundBuilder —— Checkpointer 装配。

`ATELIER_CHECKPOINTER_URL` 为空 → MemorySaver(本机默认)。
非空 → PostgresSaver.from_conn_string(...) — 与 code-writer / cookiecutter
模板同款约定(plan R13)。

继承仓库 AGENTS.md 第 4 条硬规矩。
"""
from __future__ import annotations

import os
from typing import Any


def build_checkpointer() -> Any:
    """根据环境装配 checkpointer。

    行为约定(本 Agent 与 code-writer 一致):
      - env ``ATELIER_CHECKPOINTER_URL`` 留空 → ``MemorySaver()``
      - env 设置(如 ``postgresql://...``) → ``PostgresSaver.from_conn_string(...)``
    """
    url = os.getenv("ATELIER_CHECKPOINTER_URL", "").strip()
    if url:
        from langgraph.checkpoint.postgres import PostgresSaver
        return PostgresSaver.from_conn_string(url)
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


__all__ = ["build_checkpointer"]
