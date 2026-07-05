"""CompoundBuilder —— StateGraph 流程校验。

跑完 ``graph.invoke`` 或从 checkpointer ``replay`` 后,用 ``state.decisions``
里的 milestone 事件验证是否按设计拓扑走通。不需要用户额外传 log —— 图自己在
``decisions`` / ``results_log`` 里留了审计轨迹。

用法:
  - CLI ``run --verify``(默认开) 或 ``verify <thread_id>``
  - 测试里 ``assert verify_flow(out).ok``
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# happy-path 里程碑:必须按此顺序出现(允许中间夹其它事件)
HAPPY_PATH_ORDERED_MILESTONES: tuple[str, ...] = (
    "plan.parsed",
    "test.passed",
    "units.exhausted",
    "review.start",
    "review.synthesize",
    "ship.gate",
    "final_report.written",
)

# 并行评审:6 路 Send 各写一条
EXPECTED_REVIEW_DIMENSION_EVENTS = 6

# 主链路节点至少应出现在 decisions[].by 里
EXPECTED_MAIN_NODES: frozenset[str] = frozenset({
    "coordinator",
    "executor",
    "validator",
    "review_coordinator",
    "review_synthesizer",
    "shipper",
    "reporter",
})

ExpectMode = Literal["happy", "blocked", "any"]


@dataclass(slots=True)
class FlowVerifyReport:
    """流程校验结果。"""

    ok: bool
    phase: str | None
    events: list[str] = field(default_factory=list)
    nodes_touched: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "phase": self.phase,
            "events_count": len(self.events),
            "events_tail": self.events[-30:],
            "nodes_touched": self.nodes_touched,
            "issues": self.issues,
            "milestones": self.milestones,
        }

    def format_human(self) -> str:
        lines = [
            f"flow verify: {'PASS' if self.ok else 'FAIL'}",
            f"  phase: {self.phase!r}",
            f"  events: {len(self.events)}",
            f"  nodes: {', '.join(self.nodes_touched) or '(none)'}",
        ]
        for m in self.milestones:
            mark = "✓" if m.get("ok") else "✗"
            lines.append(f"  {mark} {m.get('name')}: {m.get('detail', '')}")
        for issue in self.issues:
            lines.append(f"  ! {issue}")
        return "\n".join(lines)


def _extract_events(state: dict[str, Any]) -> list[str]:
    return [str(d.get("event", "")) for d in (state.get("decisions") or []) if d.get("event")]


def _extract_nodes(state: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for d in state.get("decisions") or []:
        by = d.get("by")
        if not by:
            continue
        # reviewer[goal-alignment] → dimension_reviewer bucket
        base = str(by).split("[", 1)[0]
        if base not in seen:
            seen.append(base)
    return seen


def _check_subsequence(
    events: list[str], required: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[str]]:
    """返回 (milestones, issues)。"""
    milestones: list[dict[str, Any]] = []
    issues: list[str] = []
    pos = 0
    for name in required:
        found_at: int | None = None
        for i in range(pos, len(events)):
            if events[i] == name:
                found_at = i
                pos = i + 1
                break
        ok = found_at is not None
        milestones.append({
            "name": name,
            "ok": ok,
            "detail": f"index={found_at}" if ok else "missing or out of order",
        })
        if not ok:
            issues.append(f"milestone missing or out-of-order: {name}")
    return milestones, issues


def verify_flow(
    state: dict[str, Any],
    *,
    expect: ExpectMode = "happy",
    n_units: int | None = None,
) -> FlowVerifyReport:
    """校验一次 invoke 的最终 state(或 history 最后一条 values)。"""
    events = _extract_events(state)
    nodes = _extract_nodes(state)
    phase = state.get("phase")
    issues: list[str] = []
    milestones: list[dict[str, Any]] = []

    if expect in ("happy", "any"):
        ms, sub_issues = _check_subsequence(events, HAPPY_PATH_ORDERED_MILESTONES)
        milestones.extend(ms)
        if expect == "happy":
            issues.extend(sub_issues)

        dim_done = sum(1 for e in events if e == "review.dimension.done")
        dim_ok = dim_done >= EXPECTED_REVIEW_DIMENSION_EVENTS
        milestones.append({
            "name": "review.dimension.done×6",
            "ok": dim_ok,
            "detail": f"count={dim_done}",
        })
        if expect == "happy" and not dim_ok:
            issues.append(
                f"expected >={EXPECTED_REVIEW_DIMENSION_EVENTS} "
                f"review.dimension.done, got {dim_done}"
            )

        missing_nodes = sorted(EXPECTED_MAIN_NODES - set(nodes))
        milestones.append({
            "name": "main_nodes",
            "ok": not missing_nodes,
            "detail": f"missing={missing_nodes}" if missing_nodes else "all present",
        })
        if expect == "happy" and missing_nodes:
            issues.append(f"main chain nodes missing in decisions.by: {missing_nodes}")

        if n_units is not None and expect == "happy":
            passed = sum(1 for e in events if e == "test.passed")
            need = n_units
            tp_ok = passed >= need
            milestones.append({
                "name": f"test.passed×{need}",
                "ok": tp_ok,
                "detail": f"count={passed}",
            })
            if not tp_ok:
                issues.append(f"expected ≥{need} test.passed, got {passed}")

    if expect == "happy":
        if phase != "terminal":
            issues.append(f"expected phase=terminal, got {phase!r}")
        verdict = (state.get("final_report") or {}).get("verdict")
        if verdict != "pass":
            issues.append(f"expected final_report.verdict=pass, got {verdict!r}")

    if expect == "blocked":
        if phase not in ("blocked", "terminal"):
            issues.append(f"expected phase in (blocked, terminal), got {phase!r}")
        if "validator.failed" not in events and "ship.refused" not in events:
            issues.append("blocked path should contain validator.failed or ship.refused")

    ok = len(issues) == 0
    return FlowVerifyReport(
        ok=ok,
        phase=str(phase) if phase is not None else None,
        events=events,
        nodes_touched=nodes,
        issues=issues,
        milestones=milestones,
    )


def verify_thread_history(
    history: list[dict[str, Any]],
    *,
    expect: ExpectMode = "happy",
    n_units: int | None = None,
) -> FlowVerifyReport:
    """对 ``get_state_history`` 最后一条 values 做校验。"""
    if not history:
        return FlowVerifyReport(ok=False, phase=None, issues=["empty thread history"])
    last = history[-1]
    return verify_flow(last, expect=expect, n_units=n_units)


__all__ = [
    "FlowVerifyReport",
    "HAPPY_PATH_ORDERED_MILESTONES",
    "verify_flow",
    "verify_thread_history",
]
