"""review_diff —— baseline..HEAD patch 落盘。"""
from __future__ import annotations

import subprocess

import pytest

from compound_builder.review_diff import (
    collect_review_diff,
    export_review_diff,
    write_run_baseline,
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


def test_collect_and_export_review_patch(git_repo):
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True,
    ).strip()
    write_run_baseline(git_repo, baseline)
    (git_repo / "sorts").mkdir()
    (git_repo / "sorts" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    _git(git_repo, "add", "sorts/foo.py")
    _git(git_repo, "commit", "-m", "feat: step-01")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, text=True,
    ).strip()

    bundle = collect_review_diff(str(git_repo), baseline, head)
    assert "sorts/foo.py" in bundle.changed_files
    assert "x = 1" in bundle.patch_text

    paths = export_review_diff(git_repo, 1, bundle)
    patch = git_repo / ".compound_builder" / "review_rounds" / "r01" / "review.patch"
    assert patch.is_file()
    assert "x = 1" in patch.read_text(encoding="utf-8")
    assert paths["patch"] == str(patch)
