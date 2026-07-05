"""reporter —— manager-facing summary + 落盘 final-report。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from compound_builder.nodes import delta
from compound_builder.state import CompoundBuilderState


def _write_final_report_file(workdir: str, summary: dict[str, Any]) -> str:
    out_dir = Path(workdir) / ".compound_builder"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "final-report.json"
    out_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(out_path)


def reporter(state: CompoundBuilderState) -> dict[str, Any]:
    units = list(state.get("units") or [])
    fix_units = list(state.get("fix_units") or [])
    findings = list(state.get("review_findings") or [])
    workdir = state.get("workdir") or os.getcwd()

    passed = sum(1 for u in units if u.get("status") == "passed")
    total = len(units)
    fix_passed = sum(1 for u in fix_units if u.get("status") == "passed")
    fix_total = len(fix_units)

    decisions_so_far = list(state.get("decisions") or [])
    summary = {
        "verdict": (
            "pass"
            if state.get("phase") in ("plan_end", "terminal")
            and not state.get("last_error")
            else "fail"
        ),
        "phase": state.get("phase"),
        "units": {"total": total, "passed": passed},
        "fix_units": {"total": fix_total, "passed": fix_passed},
        "review_findings": len(findings),
        "review_rounds": int(state.get("review_round", 0)),
        "repair_budget_used": int(state.get("repair_budget_used", 0)),
        "review_report_path": state.get("review_report_path"),
        "fix_plan_path": state.get("fix_plan_path"),
        "decisions": decisions_so_far[-10:],
    }
    report_file = _write_final_report_file(workdir, summary)
    summary["final_report_path"] = report_file

    delta_decisions = [{
        "by": "reporter",
        "event": "final_report.written",
        "path": report_file,
    }]
    delta_results = [{"event": "reporter.done", "path": report_file}]
    return delta(
        final_report=summary,
        phase="terminal",
        decisions=delta_decisions,
        results_log=delta_results,
    )


__all__ = ["reporter"]
