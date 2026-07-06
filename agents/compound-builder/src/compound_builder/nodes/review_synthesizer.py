"""review_synthesizer —— Join 节点:聚合 findings、落盘审核报告与 fix-plan。"""
from __future__ import annotations

import os
import re
from typing import Any

from compound_builder.nodes import delta
from compound_builder.review_artifacts import (
    paths_for_round,
    write_findings_json,
    write_fix_plan_json,
    write_review_report_md,
)
from compound_builder.state import CompoundBuilderState, Finding

_SOFT_DEMOTION_DIMS = frozenset({"goal-alignment", "testing", "maintainability"})
_SEV_RANK = {"p0": 4, "p1": 3, "p2": 2, "p3": 1}


def _severity_of(f: Finding) -> str:
    return (f.get("severity") or "p3").lower()


def _norm_summary(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())[:80]


def _finding_key(f: Finding) -> tuple[str, int | None, str]:
    line = f.get("line")
    return (str(f.get("file") or ""), line if isinstance(line, int) else None, _norm_summary(str(f.get("summary") or "")))


def _merge_findings(findings: list[Finding]) -> list[Finding]:
    """同 file+line+summary 去重;冲突取更高 severity (ralph synthesizer 规则简化版)。"""
    merged: dict[tuple[str, int | None, str], Finding] = {}
    for f in findings:
        key = _finding_key(f)
        prev = merged.get(key)
        if prev is None or _SEV_RANK.get(_severity_of(f), 0) > _SEV_RANK.get(_severity_of(prev), 0):
            merged[key] = f
    return list(merged.values())


def _partition_findings(
    findings: list[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """primary (fix 候选) vs residual notes (p2/p3 soft-dimension only)。"""
    primary: list[Finding] = []
    residual: list[Finding] = []
    for f in findings:
        sev = _severity_of(f)
        dim = str(f.get("dimension") or "")
        if sev in {"p0", "p1"}:
            primary.append(f)
        elif sev in {"p2", "p3"} and dim in _SOFT_DEMOTION_DIMS:
            residual.append(f)
        else:
            primary.append(f)
    return primary, residual


def review_synthesizer(state: CompoundBuilderState) -> dict[str, Any]:
    raw = list(state.get("review_findings") or [])
    findings = _merge_findings(raw)
    primary, _residual = _partition_findings(findings)
    p0_p1 = [f for f in primary if _severity_of(f) in {"p0", "p1"}]
    round_no = int(state.get("review_round") or 1)
    workdir = state.get("workdir") or os.getcwd()
    plan = state.get("plan")
    units = list(state.get("units") or [])

    fix_plan_path: str | None = None
    if p0_p1:
        fix_plan_path = str(write_fix_plan_json(workdir, round_no, p0_p1))
    else:
        fix_plan_path = "null"

    write_findings_json(workdir, round_no, findings)
    report_path = write_review_report_md(
        workdir,
        round_no,
        plan=plan,
        units=units,
        findings=findings,
        fix_plan_path=fix_plan_path,
    )
    artifact_paths = paths_for_round(workdir, round_no)

    delta_decisions = [{
        "by": "review_synthesizer",
        "event": "review.synthesize",
        "n_findings": len(findings),
        "n_p0p1": len(p0_p1),
        "review_report": str(report_path),
        "review_findings_path": artifact_paths["review_findings"],
        "fix_plan": fix_plan_path,
    }]

    if not p0_p1:
        return delta(
            phase="review",
            fix_plan_path="null",
            review_report_path=str(report_path),
            decisions=delta_decisions,
            results_log=[{
                "event": "review.artifacts_written",
                "review_report": str(report_path),
                "fix_plan": "null",
                "n": len(findings),
            }],
        )

    fix_units = []
    for i, f in enumerate(p0_p1, 1):
        fix_units.append(
            {
                "id": f"fix-{i:02d}",
                "title": (f.get("summary") or "")[:120],
                "files": [f.get("file", "")] if f.get("file") else [],
                "approach": f.get("suggested_fix") or "",
                "test_scenarios": [],
                "verification": "",
                "status": "pending",
                "task_id": None,
                "attempt_count": 0,
                "last_error": None,
                "is_fix_unit": True,
            }
        )

    return delta(
        phase="review",
        fix_plan_path=fix_plan_path,
        review_report_path=str(report_path),
        fix_units=fix_units,
        decisions=delta_decisions,
        results_log=[{
            "event": "review.artifacts_written",
            "review_report": str(report_path),
            "fix_plan": fix_plan_path,
            "n": len(p0_p1),
        }],
    )


__all__ = ["review_synthesizer", "_merge_findings", "_partition_findings"]
