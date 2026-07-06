"""validator 节点 —— 外层 StateGraph 胶水;真正验证由 ``validator_agent`` 完成。

本模块**不是** Validator 本身:只负责 commit gate、phase 路由、写 ``test.passed/failed``。
与 ``nodes/executor.py`` 调用 ``worker.run_unit_worker`` 同理,这里调用
``run_validator_agent``(独立 ReAct Agent,可读仓库 + 跑全量测试)。
"""
from __future__ import annotations

from typing import Any

from compound_builder.git_ops import verify_unit_commit_gate
from compound_builder.nodes import delta
from compound_builder.state import CompoundBuilderState, Phase
from compound_builder.validator_agent import run_validator_agent
from compound_builder.workdir_ctx import set_workdir
from compound_builder.worker import is_dry_run


def _resume_phase_on_fail(state: CompoundBuilderState, phase: str) -> Phase:
    """失败时记下应恢复的主环 phase,避免 pass 后仍停在 validator_failed。"""
    if phase in ("unit_loop", "fix_units"):
        return phase  # type: ignore[return-value]
    return state.get("repair_resume_phase") or "unit_loop"


def _resume_phase_on_pass(state: CompoundBuilderState, phase: str) -> Phase:
    """测试通过后回到 unit_loop / fix_units,不再触发 repair_budget 计数。"""
    if phase == "validator_failed":
        return state.get("repair_resume_phase") or "unit_loop"
    return phase  # type: ignore[return-value]


def _validate_unit(state: CompoundBuilderState, unit: dict[str, Any]) -> tuple[bool, str, str]:
    """跑全量测试;返回 (passed, error_tail, command)。"""
    workdir = str(state.get("workdir") or ".")
    set_workdir(workdir)

    if is_dry_run():
        err = state.get("last_error")
        return (not err, err or "", "(dry-run)")

    commit_ok, commit_err = verify_unit_commit_gate(workdir, unit)
    if not commit_ok:
        return False, commit_err, "(commit-gate)"

    outcome = run_validator_agent(state, unit)
    if outcome.passed:
        return True, "", outcome.command
    return False, outcome.output_tail, outcome.command


def validator(state: CompoundBuilderState) -> dict[str, Any]:
    """编排节点:调用 Validator Agent;dry-run 仅检查 last_error。"""
    phase = state.get("phase")
    target_kw = "fix_units" if phase == "fix_units" else "units"
    units = state.get(target_kw) or []
    idx = state.get("current_unit_index", 0)
    if not units or idx >= len(units):
        return {}

    unit = dict(units[idx])
    passed, err_tail, command = _validate_unit(state, unit)

    if not passed:
        unit["status"] = "failed"
        unit["last_error"] = err_tail
        units2 = list(state.get(target_kw) or [])
        units2[idx] = unit
        delta_decisions = [{
            "by": "validator",
            "event": "test.failed",
            "unit": unit["id"],
            "command": command[:200],
            "error": err_tail[:500],
        }]
        delta_results = [{
            "event": "test.failed",
            "id": unit["id"],
            "command": command[:200],
            "error": err_tail[:500],
        }]
        return delta(
            phase="validator_failed",
            repair_resume_phase=_resume_phase_on_fail(state, phase or "unit_loop"),
            **{target_kw: units2},
            last_error=err_tail,
            decisions=delta_decisions,
            results_log=delta_results,
        )

    unit["status"] = "passed"
    units2 = list(state.get(target_kw) or [])
    units2[idx] = unit
    next_idx = idx + 1
    delta_decisions = [{
        "by": "validator",
        "event": "test.passed",
        "unit": unit["id"],
        "command": command[:200],
    }]
    delta_results = [{"event": "test.passed", "id": unit["id"], "next": next_idx}]
    return delta(
        phase=_resume_phase_on_pass(state, phase or "unit_loop"),
        current_unit_index=next_idx,
        **{target_kw: units2},
        last_error=None,
        decisions=delta_decisions,
        results_log=delta_results,
    )


__all__ = ["validator"]
