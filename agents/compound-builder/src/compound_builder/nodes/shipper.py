"""shipper —— final validate · status update。

按 plan:
  - 二次跑 validator(全量)。
  - 把 plan status 更新为 ``complete``(成功)或 ``blocked``(plan.blocked 路径)。
  - 把 ``state.phase`` 推为 ``plan_end`` 让 reporter 写最终报告。

注意:``decisions`` / ``results_log`` channel 用 ``Annotated[list, operator.add]``,
节点函数只返回 delta(本次新增),不返回累积列表。
"""
from __future__ import annotations

from typing import Any

from compound_builder.nodes import delta
from compound_builder.state import CompoundBuilderState


def shipper(state: CompoundBuilderState) -> dict[str, Any]:
    """Shipping gate。

    检查所有 units 是否 ``status="passed"``,有任一 failed/blocked → blocked。
    """
    units = list(state.get("units") or [])
    fix_units = list(state.get("fix_units") or [])
    bad = [u for u in units if u.get("status") not in ("passed",)]
    bad += [u for u in fix_units if u.get("status") not in ("passed",)]

    delta_decisions = [{
        "by": "shipper", "event": "ship.gate", "n_bad": len(bad),
    }]

    if bad:
        return delta(
            phase="blocked",
            last_error="shipper refused: not all units passed",
            decisions=delta_decisions,
            results_log=[{"event": "ship.refused", "n": len(bad)}],
        )

    return delta(
        phase="plan_end",
        decisions=delta_decisions,
        results_log=[{"event": "ship.passed"}],
    )


__all__ = ["shipper"]
