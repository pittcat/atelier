"""coordinator_plan —— 单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from compound_builder.coordinator_plan import parse_plan_for_coordinator
from compound_builder.tools import PlanValidationError


def test_dry_run_uses_regex_when_plan_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ATELIER_DRY_RUN", "true")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# T\n\n## Acceptance\n- ok\n\n## Scope Boundaries\n- x\n\n"
        "- [ ] step 1: foo\n",
        encoding="utf-8",
    )
    payload, source = parse_plan_for_coordinator({
        "phase": "init",
        "plan": {},
        "plan_path": str(plan),
        "workdir": str(tmp_path),
    })
    assert source == "regex"
    assert len(payload["units"]) == 1
    assert payload["units"][0]["id"] == "step-01"


def test_dry_run_prefers_injected_state_plan(monkeypatch):
    monkeypatch.setenv("ATELIER_DRY_RUN", "true")
    payload, source = parse_plan_for_coordinator({
        "phase": "init",
        "plan": {
            "title": "t",
            "acceptance": [],
            "scope_boundaries": [],
            "units": [{"id": "step-01", "title": "u1"}],
        },
        "workdir": ".",
    })
    assert source == "state"
    assert payload["units"][0]["title"] == "u1"


def test_dry_run_missing_plan_raises(monkeypatch):
    monkeypatch.setenv("ATELIER_DRY_RUN", "true")
    with pytest.raises(PlanValidationError):
        parse_plan_for_coordinator({"phase": "init", "plan": {}, "workdir": "."})


def test_ralph_fixture_regex_path():
    fixture = (
        Path(__file__).resolve().parents[1]
        / "eval"
        / "datasets"
        / "plan-ralph-units.md"
    )
    payload, source = parse_plan_for_coordinator({
        "phase": "init",
        "plan": {},
        "plan_path": str(fixture),
        "workdir": str(fixture.parent),
    })
    # dry_run default in tests via conftest
    assert source in ("regex", "state")
    assert len(payload["units"]) == 2
