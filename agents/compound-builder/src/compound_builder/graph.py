"""CompoundBuilder —— StateGraph 装配。

拓扑(plan R1-R4 + R12 + KTD-1/KTD-2/KTD-3):

  START
   └─▶ coordinator ─┬─▶ executor  ─▶ validator ─▶ coordinator (next unit)
                     ├─▶ fixer     ─▶ validator
                     ├─▶ review_coordinator ─Send(map)─▶ dimension_reviewer ×6 ─▶ review_synthesizer
                     │                                                          │
                     │                                                          └─▶ coordinator
                     ├─▶ shipper ─▶ reporter ─▶ END
                     └─▶ END (blocked)

10 个节点名称:
  coordinator / executor / validator / fixer / review_coordinator
  / dimension_reviewer / review_synthesizer / shipper / reporter / progress_steward
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from compound_builder.checkpointer import build_checkpointer
from compound_builder.interrupts import build_interrupt_map
from compound_builder.nodes.coordinator import coordinator
from compound_builder.nodes.dimension_reviewer import dimension_reviewer
from compound_builder.nodes.executor import executor
from compound_builder.nodes.fixer import fixer
from compound_builder.nodes.progress_steward import progress_steward
from compound_builder.nodes.reporter import reporter
from compound_builder.nodes.review_coordinator import DIMENSIONS, review_coordinator
from compound_builder.nodes.review_synthesizer import review_synthesizer
from compound_builder.nodes.shipper import shipper
from compound_builder.nodes.validator import validator
from compound_builder.state import CompoundBuilderState


def _after_coordinator(state: CompoundBuilderState) -> str:
    phase = state.get("phase", "init")
    if phase == "blocked":
        return "shipper"
    if phase in ("plan_end", "ship"):
        return "shipper"
    if phase == "fix_units":
        return "executor"
    if phase == "validator_failed":
        return "fixer"
    if phase == "review":
        return "review_coordinator"
    if phase == "unit_loop":
        return "executor"
    return END


def _review_fanout(state: CompoundBuilderState) -> list[Send]:
    """review_coordinator → 6 个 dimension_reviewer(Send parallel)。"""
    return [
        Send("dimension_reviewer", {"dimension": d, "state": state}) for d in DIMENSIONS
    ]


def build_graph(checkpointer: Any | None = None):
    """构造并返回 compiled LangGraph StateGraph。

    ``checkpointer=None`` 时,通过 env 决定 MemorySaver / PostgresSaver。
    """
    builder = StateGraph(CompoundBuilderState)

    builder.add_node("coordinator", coordinator)
    builder.add_node("executor", executor)
    builder.add_node("validator", validator)
    builder.add_node("fixer", fixer)
    builder.add_node("review_coordinator", review_coordinator)
    builder.add_node("dimension_reviewer", dimension_reviewer)
    builder.add_node("review_synthesizer", review_synthesizer)
    builder.add_node("shipper", shipper)
    builder.add_node("reporter", reporter)
    builder.add_node("progress_steward", progress_steward)

    # 入口 → coordinator
    builder.add_edge(START, "coordinator")

    # coordinator 条件边
    builder.add_conditional_edges(
        "coordinator",
        _after_coordinator,
        {
            "executor": "executor",
            "fixer": "fixer",
            "review_coordinator": "review_coordinator",
            "shipper": "shipper",
            END: END,
        },
    )

    # executor → validator;fixer → validator;validator → coordinator
    builder.add_edge("executor", "validator")
    builder.add_edge("fixer", "validator")
    builder.add_edge("validator", "coordinator")

    # review_coordinator → Send(map) 6 维 → join review_synthesizer
    builder.add_conditional_edges("review_coordinator", _review_fanout, ["dimension_reviewer"])
    builder.add_edge("dimension_reviewer", "review_synthesizer")
    builder.add_edge("review_synthesizer", "coordinator")

    # shipper → reporter → END
    builder.add_edge("shipper", "reporter")
    builder.add_edge("reporter", END)

    # progress_steward 作为 'log tap' 节点注册(无主链路引用;评测阶段可挂为
    # 旁路回调),不挂边。

    # Interrupt:plan R10 / AGENTS.md 规则 5 — executor(走 bash / write_file /
    # edit_file / git_commit 工具)是潜在危险节点,因此 interrupt before
    # executor 与 fixer(LangGraph 节点级近似工具 interrupt;真实 HITL 由
    # LangGraph Studio / 上层调用 ``Command(resume=...)`` 恢复)。
    interrupt_nodes: list[str] = []
    if build_interrupt_map():
        # ATELIER_INTERRUPT_DEFAULT=false 时 INTERRUPT_MAP == {}
        interrupt_nodes = ["executor", "fixer"]

    cp = checkpointer if checkpointer is not None else build_checkpointer()
    return builder.compile(
        checkpointer=cp,
        interrupt_before=interrupt_nodes or None,
    )


__all__ = ["build_graph", "DIMENSIONS"]
