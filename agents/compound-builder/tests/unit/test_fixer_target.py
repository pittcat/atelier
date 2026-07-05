"""fixer —— validator_failed 时应修复 repair_resume_phase 指向的 unit 列表。"""
from __future__ import annotations

from compound_builder.nodes.fixer import _target_units_key
from compound_builder.state import CompoundBuilderState


def test_fixer_targets_units_when_validator_failed_from_unit_loop():
    state: CompoundBuilderState = {
        "phase": "validator_failed",
        "repair_resume_phase": "unit_loop",
    }
    assert _target_units_key(state) == "units"


def test_fixer_targets_fix_units_when_validator_failed_from_fix_units():
    state: CompoundBuilderState = {
        "phase": "validator_failed",
        "repair_resume_phase": "fix_units",
    }
    assert _target_units_key(state) == "fix_units"
