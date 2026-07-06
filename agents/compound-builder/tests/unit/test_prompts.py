"""prompts —— ce-executor-serial 对齐校验。"""
from __future__ import annotations

from compound_builder.prompts import (
    DIMENSION_CHECKLISTS,
    DIMENSION_FOCUS,
    SYSTEM_PROMPT_COORDINATOR,
    SYSTEM_PROMPT_COORDINATOR_PARSE,
    SYSTEM_PROMPT_EXECUTOR,
    SYSTEM_PROMPT_FIXER,
    SYSTEM_PROMPT_VALIDATOR,
    build_dimension_reviewer_prompt,
    load_code_review_mindset,
)

_EXPECTED_DIMS = (
    "goal-alignment",
    "correctness",
    "testing",
    "maintainability",
    "project-standards",
    "adversarial",
)


def test_all_six_dimension_checklists_present():
    assert set(DIMENSION_CHECKLISTS) == set(_EXPECTED_DIMS)
    assert set(DIMENSION_FOCUS) == set(_EXPECTED_DIMS)


def test_coordinator_parse_mentions_plan():
    assert "plan" in SYSTEM_PROMPT_COORDINATOR_PARSE.lower()
    assert "Implementation Units" in SYSTEM_PROMPT_COORDINATOR_PARSE


def test_executor_tdd_and_commit():
    low = SYSTEM_PROMPT_EXECUTOR.lower()
    assert "tdd" in low
    assert "git_commit" in low
    assert "push" in low


def test_fixer_diagnose_phase():
    low = SYSTEM_PROMPT_FIXER.lower()
    assert "diagnose" in low or "causal" in low
    assert "repair_budget" in low


def test_validator_discovers_entry_points():
    low = SYSTEM_PROMPT_VALIDATOR.lower()
    assert "pytest" in low
    assert "cargo" in low


def test_dimension_reviewer_prompt_includes_checklist():
    prompt = build_dimension_reviewer_prompt("adversarial")
    assert "adversarial" in prompt
    assert "Red-Team" in prompt or "read-only" in prompt.lower()
    assert "Hidden side effects" in prompt


def test_code_review_mindset_loads():
    text = load_code_review_mindset()
    assert "LGTM" in text or "broken until proven" in text.lower()
    bundled = build_dimension_reviewer_prompt("testing")
    assert "LGTM" in bundled or "broken until proven" in bundled.lower()


def test_coordinator_routing_keywords():
    assert "repair_budget" in SYSTEM_PROMPT_COORDINATOR
    assert "fix_units" in SYSTEM_PROMPT_COORDINATOR
