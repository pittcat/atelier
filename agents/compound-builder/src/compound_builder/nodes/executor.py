"""executor —— TDD 执行 + 每 unit 强制 commit。"""
from __future__ import annotations

import uuid
from typing import Any

from compound_builder.git_ops import ensure_unit_committed, rev_parse_head
from compound_builder.nodes import delta
from compound_builder.progress import progress
from compound_builder.state import CompoundBuilderState
from compound_builder.workdir_ctx import set_workdir
from compound_builder.worker import is_dry_run, run_unit_worker


def _apply_commit_gate(
    state: CompoundBuilderState,
    unit: dict[str, Any],
    *,
    head_before: str,
) -> tuple[dict[str, Any], str | None, list[dict], list[dict]]:
    """Worker 完成后确保本 unit 有新 commit;返回 (unit, error, extra_decisions, extra_logs)。"""
    if is_dry_run():
        return unit, None, [], []

    workdir = str(state.get("workdir") or ".")
    result = ensure_unit_committed(workdir, unit, head_before)
    extra_decisions: list[dict] = []
    extra_logs: list[dict] = []

    if result.ok:
        unit = dict(unit)
        unit["commit_sha"] = result.head_after
        extra_decisions.append({
            "by": "executor",
            "event": "unit.committed",
            "id": unit.get("id"),
            "sha": result.head_after[:12],
            "auto": result.auto_committed,
            "detail": result.detail[:200],
        })
        extra_logs.append({
            "event": "unit.committed",
            "id": unit.get("id"),
            "auto": result.auto_committed,
        })
        if result.auto_committed:
            progress(
                f"executor: auto-committed unit {unit.get('id')} "
                f"({result.head_after[:8]})"
            )
        return unit, None, extra_decisions, extra_logs

    return unit, result.detail, [], []


def executor(state: CompoundBuilderState) -> dict[str, Any]:
    """执行当前 unit;结束后必须产生新 git commit(否则进 fix 环)。"""
    phase = state.get("phase", "init")
    if phase not in ("unit_loop", "fix_units"):
        return {}

    target_kw = "fix_units" if phase == "fix_units" else "units"
    units = state.get(target_kw) or []
    idx = state.get("current_unit_index", 0)
    if not units or idx >= len(units):
        delta_decisions = [{"by": "executor", "event": "units.exhausted"}]
        return delta(
            phase="review",
            decisions=delta_decisions,
            results_log=[{"event": "units.exhausted"}],
        )

    unit = dict(units[idx])
    new_unit = dict(unit)
    new_unit["status"] = "in_progress"
    new_unit["attempt_count"] = int(new_unit.get("attempt_count", 0)) + 1
    new_unit["task_id"] = new_unit.get("task_id") or str(uuid.uuid4())

    workdir = str(state.get("workdir") or ".")
    head_before = ""
    if not is_dry_run():
        set_workdir(workdir)
        head_before = rev_parse_head(workdir)
        new_unit["head_before"] = head_before

    worker_summary = ""
    worker_error: str | None = None
    if not is_dry_run():
        try:
            worker_summary = run_unit_worker(state, new_unit, mode="execute")
        except Exception as e:  # noqa: BLE001
            worker_error = str(e)

    units2 = list(state.get(target_kw) or [])
    decisions: list[dict] = [{
        "by": "executor",
        "event": f"unit.{'fix' if new_unit.get('is_fix_unit') else 'dispatched'}",
        "id": new_unit["id"],
        "task_id": new_unit["task_id"],
        "dry_run": is_dry_run(),
    }]
    results_log: list[dict] = [{
        "event": f"exec.{'fix' if new_unit.get('is_fix_unit') else 'unit'}",
        "id": new_unit["id"],
        "summary_tail": worker_summary[-500:] if worker_summary else "",
    }]

    if worker_error:
        new_unit["last_error"] = worker_error
        units2[idx] = new_unit
        decisions.append({
            "by": "executor",
            "event": "unit.worker_failed",
            "id": new_unit["id"],
            "error": worker_error,
        })
        return delta(
            **{target_kw: units2},
            last_error=worker_error,
            decisions=decisions,
            results_log=results_log,
        )

    if not is_dry_run() and head_before:
        new_unit, commit_error, commit_decisions, commit_logs = _apply_commit_gate(
            state, new_unit, head_before=head_before,
        )
        decisions.extend(commit_decisions)
        results_log.extend(commit_logs)
        if commit_error:
            new_unit["last_error"] = commit_error
            units2[idx] = new_unit
            decisions.append({
                "by": "executor",
                "event": "unit.commit_failed",
                "id": new_unit["id"],
                "error": commit_error[:500],
            })
            return delta(
                **{target_kw: units2},
                last_error=commit_error,
                decisions=decisions,
                results_log=results_log,
            )

    units2[idx] = new_unit
    return delta(
        **{target_kw: units2},
        last_error=None,
        decisions=decisions,
        results_log=results_log,
    )


__all__ = ["executor"]
