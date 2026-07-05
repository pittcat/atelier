"""validator phase —— 失败后修复通过应回到 unit_loop,不重复计 repair_budget。"""
from __future__ import annotations

from unittest.mock import patch

from compound_builder.nodes.validator import validator
from compound_builder.state import CompoundBuilderState


def _state(**overrides) -> CompoundBuilderState:
    base: CompoundBuilderState = {
        "plan": None,
        "units": [
            {
                "id": "step-01",
                "title": "u1",
                "files": [],
                "approach": "",
                "test_scenarios": [],
                "verification": "make test",
                "status": "pending",
            }
        ],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "unit_loop",
        "review_findings": [],
        "fix_plan_path": None,
        "review_round": 0,
        "repair_budget_used": 0,
        "decisions": [],
        "last_error": None,
        "messages": [],
        "results_log": [],
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


def test_validator_fail_records_resume_phase():
    state = _state(phase="unit_loop")
    with patch(
        "compound_builder.nodes.validator._validate_unit",
        return_value=(False, "boom", "pytest"),
    ):
        out = validator(state)
    assert out["phase"] == "validator_failed"
    assert out["repair_resume_phase"] == "unit_loop"


def test_validator_pass_after_failure_resumes_unit_loop():
    state = _state(
        phase="validator_failed",
        repair_resume_phase="unit_loop",
        repair_budget_used=1,
    )
    with patch(
        "compound_builder.nodes.validator._validate_unit",
        return_value=(True, "", "pytest"),
    ):
        out = validator(state)
    assert out["phase"] == "unit_loop"
    assert out["current_unit_index"] == 1
    assert out["last_error"] is None


def test_validator_fail_in_fix_units_records_resume():
    state = _state(
        phase="fix_units",
        fix_units=[{"id": "fix-01", "title": "f", "verification": "t"}],
        units=[],
        current_unit_index=0,
    )
    with patch(
        "compound_builder.nodes.validator._validate_unit",
        return_value=(False, "boom", "pytest"),
    ):
        out = validator(state)
    assert out["phase"] == "validator_failed"
    assert out["repair_resume_phase"] == "fix_units"
