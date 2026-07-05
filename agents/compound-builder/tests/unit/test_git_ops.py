"""git_ops —— 每 unit commit 门禁。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from compound_builder.git_ops import (
    default_commit_message,
    ensure_unit_committed,
    has_new_commit_since,
    rev_parse_head,
    verify_unit_commit_gate,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README").write_text("init\n", encoding="utf-8")
    _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_default_commit_message():
    msg = default_commit_message({
        "id": "step-01",
        "title": "骨架",
        "files": ["sorts/foo.py"],
    })
    assert msg == "feat(sorts): step-01 骨架"


def test_ensure_unit_committed_auto_commit(git_repo: Path):
    head_before = rev_parse_head(str(git_repo))
    (git_repo / "sorts").mkdir()
    (git_repo / "sorts" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    unit = {
        "id": "step-01",
        "title": "add foo",
        "files": ["sorts/foo.py"],
    }
    result = ensure_unit_committed(str(git_repo), unit, head_before)
    assert result.ok
    assert result.auto_committed
    assert has_new_commit_since(str(git_repo), head_before)


def test_verify_unit_commit_gate_blocks_without_commit(git_repo: Path):
    head_before = rev_parse_head(str(git_repo))
    unit = {"id": "step-02", "head_before": head_before}
    ok, err = verify_unit_commit_gate(str(git_repo), unit)
    assert not ok
    assert "commit gate" in err


def test_verify_unit_commit_gate_passes_after_commit(git_repo: Path):
    head_before = rev_parse_head(str(git_repo))
    (git_repo / "a.txt").write_text("a", encoding="utf-8")
    _git(git_repo, "add", "a.txt")
    _git(git_repo, "commit", "-m", "feat: step-01 add a")
    unit = {"id": "step-01", "head_before": head_before}
    ok, err = verify_unit_commit_gate(str(git_repo), unit)
    assert ok
    assert err == ""
