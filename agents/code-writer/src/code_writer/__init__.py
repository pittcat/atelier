"""Code Writer 包入口。

注意：`agent` 是 LangGraph 的图入口（`langgraph.json:graphs.<slug>`），
但**顶层不再 eager import**它——避免在仅做单元测试或没有 LLM provider
的环境里因为 import deepagents 失败而崩。

访问方式：
    from code_writer.agent import agent  # 显式触发
    from code_writer import build_agent   # 工厂函数，运行时再调
"""

from __future__ import annotations

__all__ = ["agent", "build_agent"]
__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy-import agent 以避免在测试环境触发 deepagents 顶层 import。"""
    if name == "agent":
        from code_writer.agent import agent as _a
        return _a
    if name == "build_agent":
        from code_writer.agent import build_agent as _b
        return _b
    raise AttributeError(f"module 'code_writer' has no attribute {name!r}")
