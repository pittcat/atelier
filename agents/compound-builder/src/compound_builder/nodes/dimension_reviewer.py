"""dimension_reviewer —— 6 维评审并行节点(Send 注入 dimension)。"""
from __future__ import annotations

from typing import Any

from compound_builder.prompts import DIMENSION_DESCRIPTIONS
from compound_builder.review_worker import run_dimension_review
from compound_builder.state import CompoundBuilderState

__all__ = ["dimension_reviewer", "DIMENSION_DESCRIPTIONS"]


def dimension_reviewer(payload: dict[str, Any]) -> dict[str, Any]:
    """单维度 review:LLM 读 diff(或 dry-run 静态检查),返回 findings delta。"""
    dim = str(payload.get("dimension") or "unknown")
    state: CompoundBuilderState = payload.get("state") or {}
    findings = run_dimension_review(dim, state)
    return {
        "review_findings": findings,
        "decisions": [{
            "by": f"reviewer[{dim}]",
            "event": "review.dimension.done",
            "n": len(findings),
        }],
    }
