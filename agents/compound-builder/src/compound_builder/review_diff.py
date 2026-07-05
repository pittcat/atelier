"""Review diff —— baseline SHA 到 HEAD 的整段 patch 收集与落盘。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from compound_builder.git_ops import rev_parse_head
from compound_builder.review_artifacts import review_round_dir
from compound_builder.state import CompoundBuilderState


@dataclass(frozen=True)
class ReviewDiffBundle:
    baseline_sha: str
    head_sha: str
    patch_text: str
    stat_text: str
    changed_files: list[str]


def _run_git(workdir: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def resolve_review_baseline(state: CompoundBuilderState, workdir: str) -> str:
    """Run 开始时写入的 ``review_baseline_sha``(plan.parsed 时刻的 HEAD)。"""
    baseline = (state.get("review_baseline_sha") or "").strip()
    if baseline:
        return baseline
    for u in state.get("units") or []:
        hb = (u.get("head_before") or "").strip()
        if hb:
            return hb
    return rev_parse_head(workdir) or ""


def collect_review_diff(
    workdir: str,
    baseline_sha: str,
    head_sha: str | None = None,
) -> ReviewDiffBundle:
    """收集 ``baseline_sha..head_sha`` 的 stat + patch + 变更文件列表。"""
    head = (head_sha or rev_parse_head(workdir) or "").strip()
    baseline = baseline_sha.strip()

    if not baseline or not head:
        return ReviewDiffBundle(baseline, head, "", "", [])

    if baseline == head:
        _, stat = _run_git(workdir, "diff", "--stat", "HEAD")
        _, patch = _run_git(workdir, "diff", "HEAD")
        _, names = _run_git(workdir, "diff", "--name-only", "HEAD")
    else:
        _, stat = _run_git(workdir, "diff", "--stat", f"{baseline}..{head}")
        _, patch = _run_git(workdir, "diff", f"{baseline}..{head}")
        _, names = _run_git(workdir, "diff", "--name-only", f"{baseline}..{head}")

    changed = [
        ln.strip()
        for ln in names.splitlines()
        if ln.strip() and not ln.startswith("(")
    ]
    return ReviewDiffBundle(baseline, head, patch, stat, changed)


def export_review_diff(
    workdir: str | Path,
    round_no: int,
    bundle: ReviewDiffBundle,
) -> dict[str, str]:
    """落盘 review 用 diff 产物,供六维 reviewer 与人工查阅。"""
    out_dir = review_round_dir(workdir, round_no)
    paths = {
        "baseline_sha": str(out_dir / "review-baseline.sha"),
        "head_sha": str(out_dir / "review-head.sha"),
        "patch": str(out_dir / "review.patch"),
        "stat": str(out_dir / "review-diff-stat.txt"),
        "manifest": str(out_dir / "review-manifest.json"),
    }
    Path(paths["baseline_sha"]).write_text(bundle.baseline_sha + "\n", encoding="utf-8")
    Path(paths["head_sha"]).write_text(bundle.head_sha + "\n", encoding="utf-8")
    Path(paths["patch"]).write_text(bundle.patch_text or "(empty patch)\n", encoding="utf-8")
    Path(paths["stat"]).write_text(bundle.stat_text or "(empty)\n", encoding="utf-8")
    Path(paths["manifest"]).write_text(
        json.dumps(
            {
                "baseline_sha": bundle.baseline_sha,
                "head_sha": bundle.head_sha,
                "changed_files": bundle.changed_files,
                "patch_path": paths["patch"],
                "patch_bytes": len(bundle.patch_text.encode("utf-8")),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return paths


def write_run_baseline(workdir: str | Path, baseline_sha: str) -> Path:
    """Run 启动时写入 baseline(与 state.review_baseline_sha 同步)。"""
    root = Path(workdir) / ".compound_builder"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "run-baseline.sha"
    p.write_text(baseline_sha.strip() + "\n", encoding="utf-8")
    return p


__all__ = [
    "ReviewDiffBundle",
    "collect_review_diff",
    "export_review_diff",
    "resolve_review_baseline",
    "write_run_baseline",
]
