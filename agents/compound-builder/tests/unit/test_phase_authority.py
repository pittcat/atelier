"""phase_authority —— 状态机转换单元测试。

按 plan R3 + U2 coordinator 节点的逻辑。
"""
from __future__ import annotations

from compound_builder.nodes.coordinator import coordinator
from compound_builder.state import CompoundBuilderState


def _empty_state(**overrides):
    base: CompoundBuilderState = {
        "plan": None,
        "units": [],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "init",
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


def test_init_phase_parses_plan_with_state_plan_injected():
    """init 阶段,state.plan 已由 caller 注入(coordinator 不调用 LLM,这是
    U3 时 parse_plan 工具的 hook)。"""
    state = _empty_state(
        phase="init",
        plan={
            "title": "x",
            "acceptance": [],
            "scope_boundaries": [],
            "units": [
                {
                    "id": "step-01",
                    "title": "u1",
                    "files": [],
                    "approach": "",
                    "test_scenarios": [],
                    "verification": "",
                }
            ],
        },
    )
    out = coordinator(state)
    assert out["phase"] == "unit_loop"
    assert len(out["units"]) == 1


def test_coordinator_init_plan_missing_blocks():
    """init 阶段,plan 缺失 → plan.blocked。"""
    state = _empty_state(phase="init", plan=None)
    out = coordinator(state)
    assert out["phase"] == "blocked"


def test_validator_failed_within_budget_routes_to_fixer():
    """validator_failed + budget ≤ REPAIR_BUDGET → 保持 validator_failed(graph→fixer)。"""
    state = _empty_state(
        phase="validator_failed",
        repair_budget_used=1,
        last_error="some failure",
    )
    out = coordinator(state)
    assert out["phase"] == "validator_failed"
    assert out["repair_budget_used"] == 2


def test_validator_failed_exhausts_budget_blocks():
    """validator_failed 超 REPAIR_BUDGET → blocked。"""
    state = _empty_state(
        phase="validator_failed",
        repair_budget_used=2,
        last_error="still failing",
    )
    out = coordinator(state)
    assert out["phase"] == "validator_failed"
    assert out["repair_budget_used"] == 3
    state.update(out)
    state["phase"] = "validator_failed"
    out = coordinator(state)
    assert out["phase"] == "blocked"
