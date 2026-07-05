"""progress_steward —— 当前 LLM 未产生时,本节点只承担「进度打点」职责。

真实场景:每个 unit 的执行结果(executor / validator 前后)都打点上传到
LangSmith trace,这里是占位 hook。返回 ``{}``,不修改 state。
"""
from __future__ import annotations

from typing import Any

from compound_builder.state import CompoundBuilderState


def progress_steward(state: CompoundBuilderState) -> dict[str, Any]:
    return {}


__all__ = ["progress_steward"]
