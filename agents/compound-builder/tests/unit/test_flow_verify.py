"""flow_verify —— 单元测试。"""
from __future__ import annotations

from compound_builder.flow_verify import verify_flow


def _minimal_terminal_state(*, n_units: int = 1) -> dict:
    events = [
        "plan.parsed",
        "route.unit_loop",
        "unit.dispatched",
        "test.passed",
        "units.exhausted",
        "review.start",
        *(["review.dimension.done"] * 6),
        "review.synthesize",
        "review.complete",
        "pre_ship",
        "ship.gate",
        "final_report.written",
    ]
    if n_units > 1:
        events = (
            ["plan.parsed", "route.unit_loop"]
            + ["unit.dispatched", "test.passed"] * n_units
            + events[4:]
        )
    decisions = []
    node_map = {
        "plan.parsed": "coordinator",
        "test.passed": "validator",
        "units.exhausted": "executor",
        "review.start": "review_coordinator",
        "review.dimension.done": "reviewer[goal-alignment]",
        "review.synthesize": "review_synthesizer",
        "ship.gate": "shipper",
        "final_report.written": "reporter",
    }
    for e in events:
        decisions.append({"by": node_map.get(e, "coordinator"), "event": e})

    return {
        "phase": "terminal",
        "final_report": {"verdict": "pass"},
        "decisions": decisions,
        "plan": {"units": [{"id": f"step-{i+1:02d}"} for i in range(n_units)]},
    }


def test_verify_flow_happy_pass():
    report = verify_flow(_minimal_terminal_state(), expect="happy", n_units=1)
    assert report.ok
    assert report.phase == "terminal"


def test_verify_flow_missing_milestone_fails():
    state = _minimal_terminal_state()
    state["decisions"] = [d for d in state["decisions"] if d["event"] != "review.start"]
    report = verify_flow(state, expect="happy", n_units=1)
    assert not report.ok
    assert any("review.start" in i for i in report.issues)


def test_verify_flow_wrong_phase_fails():
    state = _minimal_terminal_state()
    state["phase"] = "review"
    report = verify_flow(state, expect="happy", n_units=1)
    assert not report.ok
