"""CompoundBuilder —— StateGraph 状态 schema。

按 plan R12:
  plan / plan_path / units / current_unit_index / workdir / phase / review_findings /
  fix_plan_path / review_round / repair_budget_used / decisions / messages

注:``review_findings`` / ``decisions`` / ``results_log`` / ``messages`` 必须用
``Annotated[list, operator.add]`` —— 6 维 reviewer 并行写入时,LangGraph 会
merge(而非覆盖)。这是 LastValue channel 的硬性要求。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from typing_extensions import TypedDict


# ============================================================
# Phase authority (plan R3) — SSOT, coordinator 节点据此决定可发事件
# ============================================================
Phase = Literal[
    "init",
    "unit_loop",
    "validator_failed",
    "review",
    "fix_units",
    "plan_end",
    "ship",
    "blocked",
    "terminal",
]


# ============================================================
# Plan / Unit 数据 schema(R5-R7)
# ============================================================
class Unit(TypedDict, total=False):
    id: str
    title: str
    files: list[str]
    approach: str
    test_scenarios: list[str]
    verification: str
    status: Literal["pending", "in_progress", "passed", "failed", "blocked"]
    task_id: str | None
    attempt_count: int
    last_error: str | None
    is_fix_unit: bool
    head_before: str | None
    commit_sha: str | None


class Plan(TypedDict, total=False):
    title: str
    acceptance: list[str]
    scope_boundaries: list[str]
    units: list[Unit]


class Finding(TypedDict, total=False):
    dimension: Literal[
        "goal-alignment",
        "correctness",
        "testing",
        "maintainability",
        "project-standards",
        "adversarial",
    ]
    severity: Literal["p0", "p1", "p2", "p3"]
    file: str
    line: int | None
    summary: str
    suggested_fix: str | None


class CompoundBuilderState(TypedDict, total=False):
    plan: Plan
    plan_path: str  # 原始 plan.md 绝对路径;coordinator init 读此文件(LLM 解析)
    units: list[Unit]
    fix_units: list[Unit]
    current_unit_index: int
    workdir: str
    phase: Phase
    # validator_failed 时记录应恢复的 phase(unit_loop / fix_units),供 pass 后回到主环
    repair_resume_phase: Phase
    # 列表字段并行写入(6 维 reviewer / 多节点同时回写)
    review_findings: Annotated[list[Finding], operator.add]
    fix_plan_path: str | None
    review_report_path: str | None
    review_baseline_sha: str | None
    review_head_sha: str | None
    review_patch_path: str | None
    review_round: int
    repair_budget_used: int
    decisions: Annotated[list[dict], operator.add]
    last_error: str | None
    messages: Annotated[list[Any], operator.add]
    results_log: Annotated[list[dict], operator.add]
    final_report: dict


__all__ = [
    "Phase",
    "Unit",
    "Plan",
    "Finding",
    "CompoundBuilderState",
]
