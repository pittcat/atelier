"""Interrupt 映射。

依据 AGENTS.md 规则：
  - bash          → 批准 / 拒绝 / 修改
  - write_file    → 批准 / 拒绝
  - edit_file     → 批准 / 拒绝
  - git_commit    → 批准 / 拒绝
"""

from __future__ import annotations


INTERRUPT_MAP: dict = {
    "bash":       {"allowed_decisions": ["approve", "edit", "reject"]},
    "write_file": {"allowed_decisions": ["approve", "reject"]},
    "edit_file":  {"allowed_decisions": ["approve", "reject"]},
    "git_commit": {"allowed_decisions": ["approve", "reject"]},
    # 注意：git_push 故意不出现 → 主代理根本看不到这个工具。
}
