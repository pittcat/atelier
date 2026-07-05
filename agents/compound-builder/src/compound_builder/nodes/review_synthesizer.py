"""review_synthesizer —— Join 节点:聚合 findings、落盘审核报告与 fix-plan。"""
from __future__ import annotations

import os
from typing import Any

from compound_builder.nodes import delta
from compound_builder.review_artifacts import (
    paths_for_round,
    write_findings_json,
    write_fix_plan_json,
    write_review_report_md,
)
from compound_builder.state import CompoundBuilderState, Finding


def _severity_of(f: Finding) -> str:
    return (f.get("severity") or "p3").lower()


def review_synthesizer(state: CompoundBuilderState) -> dict[str, Any]:
    findings = list(state.get("review_findings") or [])
    p0_p1 = [f for f in findings if _severity_of(f) in {"p0", "p1"}]
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


__all__ = ["review_synthesizer"]
