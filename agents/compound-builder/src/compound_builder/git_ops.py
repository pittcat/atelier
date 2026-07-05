"""Git 操作 —— 每 unit 一次 commit 门禁与自动兜底 commit。"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UnitCommitResult:
    ok: bool
    head_before: str
    head_after: str
    detail: str
    auto_committed: bool = False


def _run_git(workdir: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, blob


def rev_parse_head(workdir: str) -> str:
    code, out = _run_git(workdir, "rev-parse", "HEAD")
    if code != 0:
        return ""
    return out.strip()


def working_tree_dirty(workdir: str) -> bool:
    code, out = _run_git(workdir, "status", "--porcelain")
    return code == 0 and bool(out.strip())


def has_new_commit_since(workdir: str, head_before: str) -> bool:
    if not head_before:
        return False
    head_after = rev_parse_head(workdir)
    return bool(head_after) and head_after != head_before


def default_commit_message(unit: dict[str, Any]) -> str:
    uid = str(unit.get("id") or "step-??")
    title = str(unit.get("title") or "unit work")[:80]
    files = unit.get("files") or []
    scope = "compound"
    if files:
        first = Path(str(files[0]))
        scope = first.parts[0] if first.parts else "compound"
    prefix = "fix" if unit.get("is_fix_unit") else "feat"
    return f"{prefix}({scope}): {uid} {title}"


def _paths_to_stage(unit: dict[str, Any], workdir: str) -> list[str]:
    """Unit 声明的文件 + 同目录下常见测试路径。"""
    paths: list[str] = []
    for raw in unit.get("files") or []:
        p = Path(str(raw))
        paths.append(str(p))
        if p.parent != Path("."):
            paths.append(str(p.parent))
    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for item in paths:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    if unique:
        return unique
    return []


def ensure_unit_committed(
    workdir: str,
    unit: dict[str, Any],
    head_before: str,
) -> UnitCommitResult:
    """保证本 unit 结束后 HEAD 前进;必要时自动 add+commit。"""
    head_now = rev_parse_head(workdir)
    if not head_now:
        return UnitCommitResult(
            ok=False,
            head_before=head_before,
            head_after="",
            detail="git repository not available in workdir",
        )

    if has_new_commit_since(workdir, head_before):
        return UnitCommitResult(
            ok=True,
            head_before=head_before,
            head_after=head_now,
            detail="commit already created by worker",
            auto_committed=False,
        )

    if not working_tree_dirty(workdir):
        return UnitCommitResult(
            ok=False,
            head_before=head_before,
            head_after=head_now,
            detail=(
                f"unit {unit.get('id')}: no new commit and no uncommitted changes "
                f"(HEAD {head_before[:8]})"
            ),
        )

    message = default_commit_message(unit)
    stage = _paths_to_stage(unit, workdir)
    if stage:
        code, add_out = _run_git(workdir, "add", "--", *stage)
        if code != 0:
            code, add_out = _run_git(workdir, "add", "-A")
    else:
        code, add_out = _run_git(workdir, "add", "-A")

    commit_code, commit_out = _run_git(workdir, "commit", "-m", message)
    head_after = rev_parse_head(workdir)

    if commit_code != 0 or not has_new_commit_since(workdir, head_before):
        return UnitCommitResult(
            ok=False,
            head_before=head_before,
            head_after=head_after or head_now,
            detail=(
                f"auto-commit failed for unit {unit.get('id')}: "
                f"{(commit_out or add_out)[-500:]}"
            ),
        )

    return UnitCommitResult(
        ok=True,
        head_before=head_before,
        head_after=head_after,
        detail=f"auto-committed: {message}",
        auto_committed=True,
    )


def verify_unit_commit_gate(
    workdir: str,
    unit: dict[str, Any],
) -> tuple[bool, str]:
    """Validator 门禁:本 unit 必须相对 head_before 有新 commit。"""
    head_before = str(unit.get("head_before") or "")
    if not head_before:
        return True, ""
    if has_new_commit_since(workdir, head_before):
        return True, ""
    return (
        False,
        f"unit {unit.get('id')}: commit gate failed — no new commit since "
        f"{head_before[:8]} (per-unit commit required before full-suite test)",
    )


__all__ = [
    "UnitCommitResult",
    "default_commit_message",
    "ensure_unit_committed",
    "has_new_commit_since",
    "rev_parse_head",
    "verify_unit_commit_gate",
    "working_tree_dirty",
]
