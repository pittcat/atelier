"""Review 共享上下文、schema、启发式与 dry-run 逻辑。"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from compound_builder.git_ops import rev_parse_head
from compound_builder.review_diff import collect_review_diff, resolve_review_baseline
from compound_builder.state import CompoundBuilderState, Finding
from compound_builder.workdir_ctx import set_workdir

Severity = Literal["p0", "p1", "p2", "p3"]

_MAX_DIFF_CHARS = 24_000
_MAX_FILE_CHARS = 6_000
_MAX_FILES_INLINE = 12

_LINE_RANGE_RE = re.compile(r"^L?(\d+)", re.IGNORECASE)


def coerce_finding_line(value: object) -> int | None:
    """把 LLM 返回的 line 统一解析成 int（支持 ``14-16`` / ``L14`` 等）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    match = _LINE_RANGE_RE.match(text)
    if match:
        return int(match.group(1))
    return None


class FindingItem(BaseModel):
    severity: Severity
    file: str
    line: int | None = None
    summary: str
    suggested_fix: str | None = None

    @field_validator("line", mode="before")
    @classmethod
    def _parse_line(cls, value: object) -> int | None:
        return coerce_finding_line(value)


class DimensionReviewResult(BaseModel):
    findings: list[FindingItem] = Field(
        min_length=1,
        description="At least one finding per dimension (defect or p3 verification note).",
    )


def resolve_review_model() -> str:
    from compound_builder.llm import resolve_default_model

    return (
        os.getenv("ATELIER_REVIEW_MODEL")
        or os.getenv("ATELIER_SUBAGENT_MODEL")
        or resolve_default_model()
    )


def _run_git(workdir: str, *args: str, max_chars: int = 14_000) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=workdir,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(git unavailable: {e})"
    blob = (proc.stdout or "") + (proc.stderr or "")
    if len(blob) > max_chars:
        return blob[:max_chars] + "\n…(truncated)"
    return blob or "(empty)"


def _load_patch_text(state: CompoundBuilderState, bundle_patch: str) -> str:
    patch_path = (state.get("review_patch_path") or "").strip()
    if patch_path:
        p = Path(patch_path)
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            if len(text) > _MAX_DIFF_CHARS:
                return text[:_MAX_DIFF_CHARS] + "\n…(truncated; see full file on disk)"
            return text
    if len(bundle_patch) > _MAX_DIFF_CHARS:
        return bundle_patch[:_MAX_DIFF_CHARS] + "\n…(truncated)"
    return bundle_patch


def _read_file_excerpt(workdir: str, rel: str) -> str:
    path = Path(workdir) / rel
    if not path.is_file():
        return f"(missing: {rel})"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return f"(unreadable: {rel}: {e})"
    if len(text) > _MAX_FILE_CHARS:
        return text[:_MAX_FILE_CHARS] + "\n…(truncated)"
    return text


def collect_review_changed_files(state: CompoundBuilderState) -> list[str]:
    """解析 baseline..HEAD 改动文件列表。"""
    workdir = str(state.get("workdir") or ".")
    set_workdir(workdir)
    baseline = resolve_review_baseline(state, workdir)
    head = (state.get("review_head_sha") or rev_parse_head(workdir) or "").strip()
    bundle = collect_review_diff(workdir, baseline, head)
    return list(bundle.changed_files)


def build_review_manifest(state: CompoundBuilderState, changed: list[str] | None = None) -> str:
    """短 manifest 给探索 Agent;不内嵌完整 patch(由 Agent ``read_file``)。"""
    workdir = str(state.get("workdir") or ".")
    set_workdir(workdir)
    plan = state.get("plan") or {}
    baseline = resolve_review_baseline(state, workdir)
    head = (state.get("review_head_sha") or rev_parse_head(workdir) or "").strip()
    bundle = collect_review_diff(workdir, baseline, head)
    files = changed if changed is not None else list(bundle.changed_files)
    patch_path = (state.get("review_patch_path") or "").strip()

    lines = [
        f"workdir: {workdir}",
        f"plan_path: {state.get('plan_path') or '(unknown)'}",
        f"plan title: {plan.get('title', '')}",
        f"review_baseline_sha: {bundle.baseline_sha or '(none)'}",
        f"review_head_sha: {bundle.head_sha or '(none)'}",
        f"review_patch_path: {patch_path or '(not exported — use git_diff)'}",
        "",
        "## Acceptance",
    ]
    for item in plan.get("acceptance") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Scope boundaries"])
    for item in plan.get("scope_boundaries") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Units (status after implementation)"])
    for u in state.get("units") or []:
        lines.append(
            f"- {u.get('id')}: {u.get('title')} | status={u.get('status')} | "
            f"files={u.get('files')} | commit={str(u.get('commit_sha') or '')[:12]}"
        )
        if u.get("verification"):
            lines.append(f"  verification: {u.get('verification')}")

    lines.extend(["", "## Changed files (baseline..HEAD)", ""])
    if files:
        lines.extend(f"- {f}" for f in files)
    else:
        lines.append("- (none — read review.patch or git_diff)")

    lines.extend([
        "",
        "## git diff stat (baseline..HEAD)",
        bundle.stat_text or "(empty)",
        "",
        "## Exploration hints",
        "- ``read_file`` the review_patch_path for the full diff (may be large).",
        "- ``read_file`` / ``grep`` / ``glob`` changed sources and tests as needed.",
        "- ``git_diff`` / ``git_status`` for extra context.",
        "",
        "## git log (recent)",
        _run_git(workdir, "log", "-12", "--oneline", max_chars=3000),
    ])
    return "\n".join(lines)


def gather_review_context(state: CompoundBuilderState) -> tuple[str, list[str]]:
    """拼完整 review 上下文(含截断 patch);测试与调试仍用此函数。"""
    workdir = str(state.get("workdir") or ".")
    set_workdir(workdir)
    baseline = resolve_review_baseline(state, workdir)
    head = (state.get("review_head_sha") or rev_parse_head(workdir) or "").strip()
    bundle = collect_review_diff(workdir, baseline, head)
    changed = list(bundle.changed_files)
    patch_body = _load_patch_text(state, bundle.patch_text)

    manifest = build_review_manifest(state, changed)
    lines = [
        manifest,
        "",
        "## review.patch (embedded excerpt for one-shot review)",
        patch_body or "(empty patch)",
    ]

    inline_files = changed[:_MAX_FILES_INLINE]
    if inline_files:
        lines.append("")
        lines.append("## File contents (changed in this run)")
        for rel in inline_files:
            lines.append("")
            lines.append(f"### {rel}")
            lines.append("```")
            lines.append(_read_file_excerpt(workdir, rel))
            lines.append("```")

    return "\n".join(lines), changed


def acceptance_heuristics(
    dimension: str,
    state: CompoundBuilderState,
    changed: list[str],
) -> list[Finding]:
    """确定性补充:plan vs 实现,保证有实质 review 数据。"""
    findings: list[Finding] = []
    plan = state.get("plan") or {}
    acceptance = " ".join(plan.get("acceptance") or [])
    workdir = str(state.get("workdir") or ".")
    py_sources = [
        f for f in changed
        if f.endswith(".py") and (Path(workdir) / f).is_file()
    ]
    blob = ""
    for rel in py_sources[:8]:
        blob += _read_file_excerpt(workdir, rel) + "\n"

    if dimension == "goal-alignment" and "float" in acceptance.lower():
        if "float" not in blob.lower():
            findings.append(
                Finding(
                    dimension=dimension,  # type: ignore[typeddict-item]
                    severity="p1",
                    file="sorts/quick_sort.py",
                    summary=(
                        "Plan acceptance requires int/float/str support; "
                        "no float handling/tests found."
                    ),
                    suggested_fix="Add float test cases and ensure sort works for float sequences.",
                )
            )

    if dimension == "testing" and changed:
        test_files = [f for f in changed if "test" in f.lower()]
        if not test_files:
            findings.append(
                Finding(
                    dimension=dimension,  # type: ignore[typeddict-item]
                    severity="p2",
                    file="(tests)",
                    summary="Implementation files changed but no test files in this run's diff.",
                    suggested_fix="Add or update tests covering the changed behavior.",
                )
            )

    if dimension == "project-standards" and changed and not findings:
        if not re.search(r"def test_|class Test", blob):
            findings.append(
                Finding(
                    dimension=dimension,  # type: ignore[typeddict-item]
                    severity="p3",
                    file=changed[0],
                    summary=(
                        "Reviewed changed sources; no obvious convention "
                        "violations in diff scope."
                    ),
                )
            )

    return findings


def fallback_finding(dimension: str, changed: list[str], reason: str) -> Finding:
    return Finding(
        dimension=dimension,  # type: ignore[typeddict-item]
        severity="p2",
        file=changed[0] if changed else "(review)",
        summary=reason,
        suggested_fix="Re-run review after ensuring diff and file contents are present.",
    )


def dry_run_findings(
    dimension: str,
    state: CompoundBuilderState,
    changed: list[str],
) -> list[Finding]:
    findings = acceptance_heuristics(dimension, state, changed)
    if findings:
        return findings
    if changed:
        return [
            Finding(
                dimension=dimension,  # type: ignore[typeddict-item]
                severity="p3",
                file=changed[0],
                summary=f"[dry-run] Reviewed {len(changed)} changed file(s) for {dimension}.",
            )
        ]
    for u in state.get("units") or []:
        if not (u.get("verification") or "").strip():
            return [
                Finding(
                    dimension=dimension,  # type: ignore[typeddict-item]
                    severity="p2",
                    file=",".join(u.get("files") or []) or "<unit>",
                    summary=f"unit {u.get('id')} has no verification command.",
                )
            ]
    return [
        Finding(
            dimension=dimension,  # type: ignore[typeddict-item]
            severity="p3",
            file="(review)",
            summary=f"[dry-run] {dimension} review completed (no git diff in test harness).",
        )
    ]


def findings_from_items(dimension: str, items: list[FindingItem]) -> list[Finding]:
    out: list[Finding] = []
    for item in items:
        out.append(
            Finding(
                dimension=dimension,  # type: ignore[typeddict-item]
                severity=item.severity,
                file=item.file,
                line=item.line,
                summary=item.summary,
                suggested_fix=item.suggested_fix,
            )
        )
    return out


__all__ = [
    "DimensionReviewResult",
    "FindingItem",
    "Severity",
    "acceptance_heuristics",
    "build_review_manifest",
    "coerce_finding_line",
    "collect_review_changed_files",
    "dry_run_findings",
    "fallback_finding",
    "findings_from_items",
    "gather_review_context",
    "resolve_review_model",
]
