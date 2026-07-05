"""fixer —— 修复失败 unit + 每轮修复后 commit。"""
from __future__ import annotations

from typing import Any

from compound_builder.git_ops import ensure_unit_committed, rev_parse_head
from compound_builder.nodes import delta
from compound_builder.progress import progress
from compound_builder.state import CompoundBuilderState
from compound_builder.workdir_ctx import set_workdir
from compound_builder.worker import is_dry_run, run_unit_worker


def _target_units_key(state: CompoundBuilderState) -> str:
    phase = state.get("phase", "")
    if phase == "fix_units":
        return "fix_units"
    if phase == "validator_failed":
        return "fix_units" if state.get("repair_resume_phase") == "fix_units" else "units"
    return "units"


def fixer(state: CompoundBuilderState) -> dict[str, Any]:
    """修复失败 unit;结束后必须产生新 commit(与 executor 同门禁)。"""
    target_kw = _target_units_key(state)
    units = state.get(target_kw) or []
    idx = state.get("current_unit_index", 0)
    if not units or idx >= len(units):
        return {}

    unit = dict(units[idx])
    unit["attempt_count"] = int(unit.get("attempt_count", 0)) + 1
    units2 = list(state.get(target_kw) or [])
    units2[idx] = unit

    workdir = str(state.get("workdir") or ".")
    head_before = ""
    if not is_dry_run():
        set_workdir(workdir)
        head_before = rev_parse_head(workdir)
        unit["head_before"] = head_before
        units2[idx] = unit

    worker_error: str | None = None
    if not is_dry_run():
        try:
            run_unit_worker(state, unit, mode="fix")
        except Exception as e:  # noqa: BLE001
            worker_error = str(e)

    delta_decisions: list[dict] = [{
        "by": "fixer",
        "event": "fix.applied",
        "unit": unit["id"],
        "attempt": unit["attempt_count"],
        "dry_run": is_dry_run(),
    }]
    delta_results: list[dict] = [{
        "event": "fix.applied",
        "id": unit["id"],
        "attempt": unit["attempt_count"],
    }]

    if worker_error:
        delta_decisions.append({
            "by": "fixer",
            "event": "fix.worker_failed",
            "error": worker_error,
        })
        return delta(
            **{target_kw: units2},
            decisions=delta_decisions,
            last_error=worker_error,
            results_log=delta_results,
        )

    if not is_dry_run() and head_before:
        result = ensure_unit_committed(workdir, unit, head_before)
        if result.ok:
            unit = dict(unit)
            unit["commit_sha"] = result.head_after
            units2[idx] = unit
            delta_decisions.append({
                "by": "fixer",
                "event": "fix.committed",
                "unit": unit["id"],
                "sha": result.head_after[:12],
                "auto": result.auto_committed,
            })
            if result.auto_committed:
                progress(f"fixer: auto-committed {unit['id']} ({result.head_after[:8]})")
        else:
            delta_decisions.append({
                "by": "fixer",
                "event": "fix.commit_failed",
                "unit": unit["id"],
                "error": result.detail[:500],
            })
            return delta(
                **{target_kw: units2},
                decisions=delta_decisions,
                last_error=result.detail,
                results_log=delta_results,
            )

    return delta(
        **{target_kw: units2},
        decisions=delta_decisions,
        last_error=None,
        results_log=delta_results,
    )


__all__ = ["fixer"]
