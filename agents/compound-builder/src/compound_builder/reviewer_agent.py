"""Dimension Reviewer Agent —— 只读探索 ReAct + 结构化收尾(带校验重试)。

与 ``validator_agent`` 同级:外层 ``nodes/dimension_reviewer`` 只写
``review_findings`` → ``review_synthesizer``。
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from compound_builder.llm import get_llm
from compound_builder.progress import progress
from compound_builder.prompts import (
    build_reviewer_exploration_prompt,
    build_reviewer_structured_prompt,
)
from compound_builder.review_context import (
    DimensionReviewResult,
    FindingItem,
    acceptance_heuristics,
    build_review_manifest,
    collect_review_changed_files,
    dry_run_findings,
    fallback_finding,
    findings_from_items,
    resolve_review_model,
)
from compound_builder.state import CompoundBuilderState, Finding
from compound_builder.tools import build_tools
from compound_builder.workdir_ctx import set_workdir
from compound_builder.worker import is_dry_run

_REVIEWER_AGENT_TOOLS = frozenset({
    "read_file",
    "glob",
    "grep",
    "git_diff",
    "git_status",
})

_MAX_EXPLORATION_NOTE_CHARS = 20_000
_DEFAULT_STRUCTURED_ATTEMPTS = 2  # 初次 + 1 次带错误反馈重试


class StructuredReviewError(Exception):
    """结构化收尾在耗尽重试后仍失败。"""


def _content_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def summarize_exploration_messages(
    messages: list[Any],
    *,
    max_chars: int = _MAX_EXPLORATION_NOTE_CHARS,
) -> str:
    """从探索 Agent 消息历史提取 audit memo。"""
    parts: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", None) or getattr(msg, "role", "")
        if role not in ("ai", "assistant"):
            continue
        text = _content_str(getattr(msg, "content", "")).strip()
        if text:
            parts.append(text)
    if not parts:
        return "(exploration agent produced no narrative notes)"
    blob = "\n\n---\n\n".join(parts)
    if len(blob) > max_chars:
        return blob[:max_chars] + "\n…(truncated)"
    return blob


def _exploration_task_prompt(dimension: str, manifest: str) -> str:
    return "\n".join([
        f"Review dimension: **{dimension}**",
        "",
        "## Manifest (paths and plan context)",
        manifest,
        "",
        "## Task",
        "Explore this run's changes using read-only tools.",
        "Read ``review_patch_path`` for the full diff; drill into changed files as needed.",
        "Finish with an audit memo (path:line evidence). Do NOT output JSON findings.",
    ])


def build_reviewer_exploration_agent(dimension: str):
    """构造只读探索 ReAct Agent。"""
    from compound_builder.react_agent import build_react_agent

    tools = [t for t in build_tools() if t.name in _REVIEWER_AGENT_TOOLS]
    model = get_llm(resolve_review_model())
    return build_react_agent(
        model,
        tools,
        prompt=build_reviewer_exploration_prompt(dimension),
    )


def run_exploration_phase(
    dimension: str,
    state: CompoundBuilderState,
    manifest: str,
) -> str:
    """阶段 A:只读探索,返回 audit memo 文本。"""
    wd = set_workdir(state.get("workdir") or os.getcwd())
    progress(f"reviewer-agent[{dimension}]: read-only exploration in {wd} …")

    agent = build_reviewer_exploration_agent(dimension)
    try:
        result = agent.invoke(
            {
                "messages": [
                    ("user", _exploration_task_prompt(dimension, manifest)),
                ],
            },
            config={
                "recursion_limit": int(
                    os.getenv("ATELIER_REVIEWER_RECURSION_LIMIT", "35")
                ),
            },
        )
    except Exception as e:  # noqa: BLE001
        progress(f"reviewer-agent[{dimension}]: exploration failed ({e})")
        return f"(exploration agent error: {e})"

    messages = result.get("messages") or []
    notes = summarize_exploration_messages(messages)
    progress(f"reviewer-agent[{dimension}]: exploration memo {len(notes)} chars")
    return notes


def _structured_human_message(
    dimension: str,
    manifest: str,
    exploration_notes: str,
    changed: list[str],
    last_err: str | None,
) -> str:
    lines = [
        f"Review dimension: **{dimension}**",
        "",
        "## Review manifest",
        manifest,
        "",
        "## Exploration notes (from read-only reviewer agent)",
        exploration_notes,
        "",
        f"## Changed files ({len(changed)})",
    ]
    if changed:
        lines.extend(f"- {f}" for f in changed)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "Produce **DimensionReviewResult**: at least one finding (p0–p3).",
        "``line`` = single integer or null (not a range string).",
        "``file`` = repo-relative path; prefer changed-files list.",
    ])
    if last_err:
        lines.extend([
            "",
            "## Previous structured output REJECTED — fix and resubmit",
            last_err,
        ])
    return "\n".join(lines)


def run_structured_finalize(
    dimension: str,
    manifest: str,
    exploration_notes: str,
    changed: list[str],
    *,
    max_attempts: int | None = None,
) -> DimensionReviewResult:
    """阶段 B:structured output;失败时把校验错误喂回重试。"""
    attempts = max_attempts
    if attempts is None:
        attempts = int(
            os.getenv(
                "ATELIER_REVIEW_STRUCTURED_ATTEMPTS",
                str(_DEFAULT_STRUCTURED_ATTEMPTS),
            )
        )
    attempts = max(1, attempts)

    model = get_llm(resolve_review_model())
    structured = model.with_structured_output(DimensionReviewResult)
    system = build_reviewer_structured_prompt(dimension)
    last_err: str | None = None

    for attempt in range(1, attempts + 1):
        human = _structured_human_message(
            dimension, manifest, exploration_notes, changed, last_err,
        )
        try:
            result: DimensionReviewResult = structured.invoke(
                [SystemMessage(content=system), HumanMessage(content=human)],
            )
            if not result.findings:
                raise ValueError("findings: List should have at least 1 item")
            progress(
                f"reviewer-agent[{dimension}]: structured OK on attempt {attempt} "
                f"({len(result.findings)} finding(s))"
            )
            return result
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            progress(
                f"reviewer-agent[{dimension}]: structured attempt {attempt}/{attempts} "
                f"failed ({e})"
            )

    raise StructuredReviewError(last_err or "structured finalize failed")


def run_dimension_review_agent(
    dimension: str,
    state: CompoundBuilderState,
) -> list[Finding]:
    """运行 Dimension Reviewer Agent;**至少返回 1 条** finding。"""
    changed = collect_review_changed_files(state)
    manifest = build_review_manifest(state, changed)

    if is_dry_run():
        out = dry_run_findings(dimension, state, changed)
        progress(f"reviewer-agent[{dimension}]: {len(out)} finding(s) [dry-run]")
        return out

    exploration_notes = run_exploration_phase(dimension, state, manifest)

    llm_items: list[FindingItem] = []
    try:
        structured = run_structured_finalize(
            dimension, manifest, exploration_notes, changed,
        )
        llm_items = list(structured.findings)
    except StructuredReviewError as e:
        progress(f"reviewer-agent[{dimension}]: structured exhausted ({e})")

    out = findings_from_items(dimension, llm_items)
    out.extend(acceptance_heuristics(dimension, state, changed))

    if not out:
        out.append(
            fallback_finding(
                dimension,
                changed,
                f"Structured review failed after retries; manual {dimension} review required.",
            )
        )

    progress(f"reviewer-agent[{dimension}]: {len(out)} finding(s) total")
    return out


# 向后兼容
run_dimension_review = run_dimension_review_agent

__all__ = [
    "StructuredReviewError",
    "build_reviewer_exploration_agent",
    "run_dimension_review",
    "run_dimension_review_agent",
    "run_exploration_phase",
    "run_structured_finalize",
    "summarize_exploration_messages",
]
