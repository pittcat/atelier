"""CompoundBuilder —— Interrupt 配置。

继承仓库 AGENTS.md 第 3 条:`bash` / `write_file` / `edit_file` / `git_commit`
必须 `interrupt_on=True`。

`ATELIER_INTERRUPT_DEFAULT`(默认 `true`):`false` 时 4 工具全自动(供评测用)。
"""

from __future__ import annotations

import os
from typing import Any


DEFAULT_INTERRUPT_TOOLS: set[str] = {
    "bash",
    "write_file",
    "edit_file",
    "git_commit",
}


def build_interrupt_map(tool_names: list[str] | None = None) -> dict[str, bool]:
    """返回 ``{tool_name: True}`` 的 map;默认覆盖 4 工具。"""
    if os.getenv("ATELIER_INTERRUPT_DEFAULT", "true").lower() == "false":
        return {}
    names = tool_names or sorted(DEFAULT_INTERRUPT_TOOLS)
    return {n: True for n in names}


# 兼容旧名;U2 也可用此直接构造 StateGraph 的 interrupt_on
INTERRUPT_MAP: dict[str, Any] = build_interrupt_map()


__all__ = ["DEFAULT_INTERRUPT_TOOLS", "build_interrupt_map", "INTERRUPT_MAP"]
