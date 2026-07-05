"""review_worker —— dry-run、baseline diff、必有 findings。"""
from __future__ import annotations

import os
import subprocess

import pytest

from compound_builder.review_diff import collect_review_diff
from compound_builder.review_worker import (
    FindingItem,
    coerce_finding_line,
    gather_review_context,
    run_dimension_review,
)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@e.com")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "README").write_text("init\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_gather_review_context_includes_baseline_diff(git_repo, monkeypatch):
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True,
    ).strip()
    (git_repo / "sorts").mkdir()
    (git_repo / "sorts" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", "sorts/foo.py")
    _git(git_repo, "commit", "-m", "feat: add foo")

    state = {
        "workdir": str(git_repo),
        "review_baseline_sha": baseline,
        "plan": {
            "title": "Demo Plan",
            "acceptance": ["must pass tests"],
            "scope_boundaries": [],
            "units": [],
        },
        "units": [{"id": "step-01", "title": "u1", "status": "passed", "files": ["sorts/foo.py"]}],
    }
    ctx, changed = gather_review_context(state)
    assert "Demo Plan" in ctx
    assert "sorts/foo.py" in changed
    assert "review.patch" in ctx
    assert "x = 1" in ctx


def test_collect_review_diff_uses_baseline_range(git_repo):
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True,
    ).strip()
    (git_repo / "a.txt").write_text("a", encoding="utf-8")
    _git(git_repo, "add", "a.txt")
    _git(git_repo, "commit", "-m", "add a")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True,
    ).strip()
    bundle = collect_review_diff(str(git_repo), baseline, head)
    assert "a.txt" in bundle.changed_files


def test_coerce_finding_line_range_and_prefixes():
    assert coerce_finding_line("14-16") == 14
    assert coerce_finding_line("38-48") == 38
    assert coerce_finding_line("L12") == 12
    assert coerce_finding_line(42) == 42
    assert coerce_finding_line(None) is None
    assert coerce_finding_line("") is None


def test_finding_item_accepts_line_range_string():
    item = FindingItem(
        severity="p2",
        file="sorts/quick_sort.py",
        line="14-16",
        summary="partition edge case",
    )
    assert item.line == 14


def test_run_dimension_review_dry_run_always_returns_findings(monkeypatch):
    monkeypatch.setenv("ATELIER_DRY_RUN", "true")
    state = {
        "workdir": os.getcwd(),
        "plan": {"title": "t", "acceptance": ["int/float/str"], "scope_boundaries": []},
        "units": [
            {
                "id": "step-01",
                "title": "u1",
                "verification": "make test",
                "files": [],
            },
        ],
    }
    for dim in (
        "goal-alignment",
        "correctness",
        "testing",
        "maintainability",
        "project-standards",
        "adversarial",
    ):
        findings = run_dimension_review(dim, state)
        assert len(findings) >= 1, f"{dim} returned empty findings"
