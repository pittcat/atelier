"""向后兼容: Dimension Reviewer Agent 实现在 ``reviewer_agent.py``。"""
from compound_builder.review_context import (
    DimensionReviewResult,
    FindingItem,
    coerce_finding_line,
    gather_review_context,
    resolve_review_model,
)
from compound_builder.reviewer_agent import (
    StructuredReviewError,
    run_dimension_review,
    run_dimension_review_agent,
    run_exploration_phase,
    run_structured_finalize,
    summarize_exploration_messages,
)

__all__ = [
    "DimensionReviewResult",
    "FindingItem",
    "StructuredReviewError",
    "coerce_finding_line",
    "gather_review_context",
    "resolve_review_model",
    "run_dimension_review",
    "run_dimension_review_agent",
    "run_exploration_phase",
    "run_structured_finalize",
    "summarize_exploration_messages",
]
