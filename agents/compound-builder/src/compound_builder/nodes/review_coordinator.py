"""review_coordinator —— 导出整段 diff patch,再 fan-out 六维 review。"""
from __future__ import annotations

import os
from typing import Any

from langgraph.types import Send

from compound_builder.progress import progress
from compound_builder.review_diff import (
    collect_review_diff,
    export_review_diff,
    resolve_review_baseline,
)
from compound_builder.git_ops import rev_parse_head
from compound_builder.state import CompoundBuilderState

DIMENSIONS: list[str] = [
    "goal-alignment",
    "correctness",
    "testing",
    "maintainability",
    "project-standards",
    "adversarial",
]


def review_coordinator(state: CompoundBuilderState) -> dict[str, Any]:
    """units 完成后:baseline..HEAD 导出 review.patch,再 Send 六维 reviewer。"""
    round_no = int(state.get("review_round", 0)) + 1
    workdir = state.get("workdir") or os.getcwd()
    baseline = resolve_review_baseline(state, str(workdir))
    head = rev_parse_head(str(workdir))

    bundle = collect_review_diff(str(workdir), baseline, head)
    artifact_paths = export_review_diff(workdir, round_no, bundle)
    progress(
        f"review: exported patch {baseline[:8]}..{head[:8]} "
        f"({len(bundle.changed_files)} files) → {artifact_paths['patch']}"
    )

    state_for_reviewers: CompoundBuilderState = {
        **state,
        "phase": "review",
        "review_round": round_no,
        "review_head_sha": head,
        "review_patch_path": artifact_paths["patch"],
    }
    sends = [
        Send("dimension_reviewer", {"dimension": d, "state": state_for_reviewers})
        for d in DIMENSIONS
    ]
    delta_decisions = [{
        "by": "review_coordinator",
        "event": "review.start",
        "round": round_no,
        "baseline_sha": baseline,
        "head_sha": head,
        "review_patch": artifact_paths["patch"],
        "n_changed_files": len(bundle.changed_files),
    }]
    delta_results = [{
        "event": "review.start",
        "round": round_no,
        "patch": artifact_paths["patch"],
    }]
    return {
        "phase": "review",
        "review_round": round_no,
        "review_head_sha": head,
        "review_patch_path": artifact_paths["patch"],
        "decisions": delta_decisions,
        "results_log": delta_results,
        "goto": sends,
    }


__all__ = ["review_coordinator", "DIMENSIONS"]
