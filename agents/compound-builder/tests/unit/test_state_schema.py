"""state —— plan_path 必须留在 StateGraph schema 内。"""
from __future__ import annotations

from compound_builder.agent import build_agent


def test_invoke_preserves_plan_path():
    """LangGraph 会丢弃 schema 外的 key;plan_path 必须在 CompoundBuilderState 里。"""
    agent = build_agent()
    cfg = {"configurable": {"thread_id": "test-plan-path-preserved"}}
    plan_path = "/tmp/fake-plan.md"
    # 不真读文件:init 会 fail,但 checkpoint 第一条应仍带 plan_path
    out = agent.invoke(
        {
            "phase": "init",
            "plan": {},
            "plan_path": plan_path,
            "workdir": ".",
            "units": [],
            "fix_units": [],
            "current_unit_index": 0,
            "review_findings": [],
            "decisions": [],
            "results_log": [],
            "messages": [],
        },
        config=cfg,
    )
    # blocked 或 terminal 都应能在 history 里看到 plan_path 被 coordinator 读到
    history = list(agent.get_state_history(cfg))
    first_values = history[0].values if history else {}
    assert first_values.get("plan_path") == plan_path
