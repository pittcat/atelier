"""dimension_reviewer 节点 —— 外层 StateGraph 胶水;评审由 ``reviewer_agent`` 完成。"""
from __future__ import annotations

from typing import Any

from compound_builder.prompts import DIMENSION_DESCRIPTIONS
from compound_builder.reviewer_agent import run_dimension_review_agent
from compound_builder.state import CompoundBuilderState

__all__ = ["dimension_reviewer", "DIMENSION_DESCRIPTIONS"]


def dimension_reviewer(payload: dict[str, Any]) -> dict[str, Any]:
    """单维度 review:Reviewer Agent → findings delta → review_synthesizer。"""
    dim = str(payload.get("dimension") or "unknown")
    state: CompoundBuilderState = payload.get("state") or {}
    findings = run_dimension_review_agent(dim, state)
    return {
        "review_findings": findings,
        "decisions": [{
            "by": f"reviewer-agent[{dim}]",
            "event": "review.dimension.done",
            "n": len(findings),
        }],
    }
