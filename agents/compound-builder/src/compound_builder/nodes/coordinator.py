"""coordinator —— LLM 读 plan、拆 unit;维护 phase authority、路由下一站。"""
from __future__ import annotations

import os
from typing import Any

from compound_builder.coordinator_plan import parse_plan_for_coordinator
from compound_builder.git_ops import rev_parse_head
from compound_builder.nodes import delta
from compound_builder.review_diff import write_run_baseline
from compound_builder.state import CompoundBuilderState, Unit
from compound_builder.tools import PlanValidationError

REPAIR_BUDGET = int(os.getenv("ATELIER_REPAIR_BUDGET", "3"))


def _normalize_unit(u: dict) -> Unit:
    """补齐 Unit 字段默认值。"""
    out: Unit = {
        "id": u.get("id", f"step-{(u.get('index', 0) or 0) + 1:02d}"),
        "title": u.get("title", ""),
        "files": list(u.get("files") or []),
        "approach": u.get("approach", ""),
        "test_scenarios": list(u.get("test_scenarios") or []),
        "verification": u.get("verification", ""),
        "status": u.get("status", "pending"),
        "task_id": u.get("task_id"),
        "attempt_count": int(u.get("attempt_count", 0)),
        "last_error": u.get("last_error"),
        "is_fix_unit": bool(u.get("is_fix_unit", False)),
        "head_before": u.get("head_before"),
        "commit_sha": u.get("commit_sha"),
    }
    return out


def coordinator(state: CompoundBuilderState) -> dict[str, Any]:
    """主 coordinator:init 调 LLM 解析 plan;其余 phase 做确定性路由。"""
    phase = state.get("phase", "init")
    delta_decisions: list[dict] = []
    delta_results: list[dict] = []

    def push(event: str, **payload) -> None:
        delta_decisions.append({"by": "coordinator", "event": event, **payload})
        delta_results.append({"event": event, **payload})

    # ---- 1. init: LLM 读 plan.md → units ----
    if phase == "init":
        try:
            parsed, source = parse_plan_for_coordinator(state)
        except (PlanValidationError, Exception) as e:  # noqa: BLE001
            push("plan.parse_failed", error=str(e))
            return delta(
                phase="blocked",
                decisions=delta_decisions,
                last_error=str(e),
                results_log=delta_results,
            )
        units = [_normalize_unit(u) for u in parsed["units"]]
        workdir = str(state.get("workdir") or ".")
        baseline = rev_parse_head(workdir) or None
        if baseline:
            write_run_baseline(workdir, baseline)
        push("plan.parsed", n_units=len(units), source=source, review_baseline=baseline)
        return delta(
            phase="unit_loop",
            units=units,
            fix_units=[],
            current_unit_index=0,
            review_round=0,
            repair_budget_used=0,
            plan=parsed["plan"],
            review_baseline_sha=baseline,
            decisions=delta_decisions,
            results_log=delta_results,
        )

    # ---- 2. review 收尾:根据 fix_plan 决定 ship 或 fix_units ----
    if phase == "review" and state.get("fix_plan_path") is not None:
        fix = state.get("fix_plan_path")
        push("review.complete", fix_plan=fix)
        if fix == "null":
            return delta(phase="ship", decisions=delta_decisions, results_log=delta_results)
        fix_units = state.get("fix_units") or []
        if not fix_units:
            return delta(phase="ship", decisions=delta_decisions, results_log=delta_results)
        return delta(
            phase="fix_units",
            current_unit_index=0,
            decisions=delta_decisions,
            results_log=delta_results,
        )

    # ---- 3. validator_failed → repair_budget ----
    if phase == "validator_failed":
        budget_used = int(state.get("repair_budget_used", 0)) + 1
        push("validator.failed", budget_used=budget_used)
        if budget_used > REPAIR_BUDGET:
            return delta(
                phase="blocked",
                repair_budget_used=budget_used,
                last_error=state.get("last_error") or "repair_budget_exceeded",
                decisions=delta_decisions,
                results_log=delta_results,
            )
        # 保持 validator_failed,让 graph 条件边路由到 fixer(不是 unit_loop→executor)
        return delta(
            phase="validator_failed",
            repair_budget_used=budget_used,
            decisions=delta_decisions,
            results_log=delta_results,
        )

    # ---- 4. ship → plan_end ----
    if phase == "ship":
        push("pre_ship")
        return delta(
            phase="plan_end",
            decisions=delta_decisions,
            results_log=delta_results,
        )

    # ---- 5. fix_units 完成 → ship ----
    if phase == "fix_units":
        fix_units = state.get("fix_units") or []
        idx = state.get("current_unit_index", 0)
        if idx >= len(fix_units):
            push("fix_units.complete")
            return delta(phase="ship", decisions=delta_decisions, results_log=delta_results)
        return {}

    # ---- 6. unit_loop → 条件边进 executor ----
    if phase == "unit_loop":
        return delta(
            decisions=[{"by": "coordinator", "event": "route.unit_loop"}],
            results_log=[{"event": "route.unit_loop"}],
        )

    return {}


__all__ = ["coordinator", "REPAIR_BUDGET"]
