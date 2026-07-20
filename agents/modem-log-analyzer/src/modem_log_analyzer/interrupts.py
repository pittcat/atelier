"""ModemLogAnalyzer —— Interrupt 映射。

按 Plan / AGENTS.md 规则:
  - 主代理本身没有 bash / write_file / git_commit / git_push 工具,
    因此 INTERRUPT_MAP 暂为空。
  - 后续 Unit 5 接入控制脚本日志请求(interrupt_on 由 deepagents 在 graph 上装配)。

Unit 1 阶段:显式声明"空 interrupt 映射",便于测试与 layout smoke 校验。
"""

from __future__ import annotations

INTERRUPT_MAP: dict = {
    # 注意:本 Agent 是只读分析 Agent,不暴露危险工具。
    # 控制脚本日志的"按需请求"由 LangGraph interrupt()/Command(resume=...) 协议承担,
    # 不通过 interrupt_on 工具列表。
}


__all__ = ["INTERRUPT_MAP"]
