"""repair_budget —— 计数与升级逻辑。

按 plan R4:repair_budget=3(可调 env ATELIER_REPAIR_BUDGET);超 → blocked。
本测试覆盖:
  - 默认 3(env 不设)。
  - 4 次失败后 blocked;3 次失败后仍 unit_loop。
"""
from __future__ import annotations

import os

from compound_builder.nodes.coordinator import coordinator, REPAIR_BUDGET


def test_default_budget_is_three():
    assert REPAIR_BUDGET == 3


def test_three_failures_in_cycle():
    state = {
        "plan": None,
        "units": [],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "validator_failed",
        "review_findings": [],
        "fix_plan_path": None,
        "review_round": 0,
        "repair_budget_used": 0,
        "decisions": [],
        "last_error": "boom",
        "messages": [],
        "results_log": [],
    }
    # 第 1 次失败 → budget=1,phase 保持 validator_failed → graph 进 fixer
    out1 = coordinator(state)
    assert out1["phase"] == "validator_failed"
    # 第 2 次失败 → budget=2
    state.update(out1)
    state["phase"] = "validator_failed"
    out2 = coordinator(state)
    assert out2["phase"] == "validator_failed"
    # 第 3 次失败 → budget=3,仍在 budget 内
    state.update(out2)
    state["phase"] = "validator_failed"
    out3 = coordinator(state)
    assert out3["phase"] == "validator_failed"
    # 第 4 次失败 → budget=4 > 3,blocked
    state.update(out3)
    state["phase"] = "validator_failed"
    out4 = coordinator(state)
    assert out4["phase"] == "blocked"
    assert out4["repair_budget_used"] == 4


def test_budget_override_via_env(monkeypatch):
    monkeypatch.setenv("ATELIER_REPAIR_BUDGET", "1")
    # 重新 import 以读取 env(模块常量 cache 在 import 时)
    import importlib
    import compound_builder.nodes.coordinator as c
    importlib.reload(c)
    assert c.REPAIR_BUDGET == 1
    state = {
        "plan": None,
        "units": [],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "validator_failed",
        "review_findings": [],
        "fix_plan_path": None,
        "review_round": 0,
        "repair_budget_used": 0,
        "decisions": [],
        "last_error": "boom",
        "messages": [],
        "results_log": [],
    }
    out = c.coordinator(state)
    # budget=1 → +1 = 1,仍 ≤ 1 → validator_failed(进 fixer)
    assert out["phase"] == "validator_failed"
    # 第 2 次失败 → budget_used = 2 > 1 → blocked
    state.update(out)
    state["phase"] = "validator_failed"
    out = c.coordinator(state)
    assert out["phase"] == "blocked"
