"""tools.py —— 单元测试。

按 plan R9 / R11:
  - tools 注册清单必须不包含 push 类。
  - discover_test_entry 优先级链正确。
  - parse_plan / validate_plan 强校验。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compound_builder.tools import (
    NoTestEntryError,
    PlanValidationError,
    build_tools,
    discover_test_entry,
    parse_plan,
    validate_plan,
)


def test_build_tools_has_no_push():
    tools = build_tools()
    names = {t.name for t in tools}
    # R9: 严禁导出 push 类工具
    forbidden = {"git_push", "git_push_tool", "git_worktree_add"}
    assert not (names & forbidden), f"forbidden tools present: {names & forbidden}"


def test_build_tools_has_required_tools():
    """R8: 必须暴露的 14 类工具全在。"""
    tools = build_tools()
    names = {t.name for t in tools}
    expected = {
        "bash", "write_file", "edit_file", "read_file",
        "glob", "grep",
        "git_commit", "git_diff",
        "discover_test_entry", "run_tests",
        "parse_plan", "validate_plan",
        "write_findings_json", "emit_state_event",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"


def test_discover_test_entry_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\n[tool.pytest]\nini=true\n', encoding="utf-8"
    )
    assert discover_test_entry.func(str(tmp_path)) == "pytest -v"  # type: ignore[attr-defined]


def test_discover_test_entry_nested_package(tmp_path: Path):
    pkg = tmp_path / "sorts"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text(
        '[project]\nname="sorts"\n[tool.pytest]\nini=true\n', encoding="utf-8"
    )
    (pkg / "tests").mkdir()
    (pkg / "tests" / "test_x.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    assert discover_test_entry.func(str(tmp_path)) == "cd sorts && pytest -v"  # type: ignore[attr-defined]


def test_discover_test_entry_makefile(tmp_path: Path):
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    assert discover_test_entry.func(str(tmp_path)) == "make test"  # type: ignore[attr-defined]


def test_discover_test_entry_no_test(tmp_path: Path):
    """无测试入口 → 返回错误文本(工具不抛异常)。"""
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    out = discover_test_entry.func(str(tmp_path))  # type: ignore[attr-defined]
    assert "error" in out.lower()
    with pytest.raises(NoTestEntryError):
        from compound_builder.tools import discover_test_entry_or_raise
        discover_test_entry_or_raise(str(tmp_path))


def test_git_commit_runs_add_first(tmp_path: Path, monkeypatch):
    import subprocess

    from compound_builder.tools import git_commit
    from compound_builder.workdir_ctx import set_workdir

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@e.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    set_workdir(str(tmp_path))
    out = git_commit.func("feat: test commit", paths=["f.txt"])  # type: ignore[attr-defined]
    assert "[git add]" in out
    assert "[git commit]" in out
    log = subprocess.run(
        ["git", "log", "-1", "--oneline"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "feat: test commit" in log.stdout


def test_parse_plan_minimal(tmp_path: Path):
    plan_md = tmp_path / "plan.md"
    plan_md.write_text(
        "# My Plan\n"
        "\n"
        "## Acceptance\n"
        "- tests pass\n"
        "\n"
        "## Scope Boundaries\n"
        "- no infra changes\n"
        "\n"
        "- [ ] step 1: add foo\n"
        "- [ ] step 2: wire bar\n",
        encoding="utf-8",
    )
    out = parse_plan.func(str(plan_md))  # type: ignore[attr-defined]
    assert out["title"] == "My Plan"
    assert out["acceptance"] == ["tests pass"]
    assert out["units"][0]["id"] == "step-01"
    assert out["units"][1]["id"] == "step-02"
    # 通过 validate_plan
    val = validate_plan.func(out)  # type: ignore[attr-defined]
    assert val["ok"] is True


def test_validate_plan_invalid():
    val = validate_plan.func({"title": "x", "acceptance": [], "scope_boundaries": [], "units": []})  # type: ignore[attr-defined]
    assert val["ok"] is False  # 空 units 列表不允许


def test_parse_plan_ralph_implementation_units(tmp_path: Path):
    """Ralph ce-plan: Implementation Units + #### stepN. 块。"""
    fixture = Path(__file__).resolve().parents[1] / "eval" / "datasets" / "plan-ralph-units.md"
    out = parse_plan.func(str(fixture))  # type: ignore[attr-defined]
    assert out["title"] == "feat: sample ralph plan"
    assert len(out["acceptance"]) == 2
    assert "core feature only" in out["scope_boundaries"]
    assert len(out["units"]) == 2
    assert out["units"][0]["id"] == "step-01"
    assert out["units"][1]["id"] == "step-02"
    assert "pkg/__init__.py" in out["units"][0]["files"]
    assert "pytest -v" in out["units"][0]["verification"]
    assert len(out["units"][0]["test_scenarios"]) == 2
    val = validate_plan.func(out)  # type: ignore[attr-defined]
    assert val["ok"] is True


def test_parse_plan_ralph_e2e_fixture():
    """真实 ralph-e2e plan(若存在)应解析出 2 个 unit。"""
    plan = Path("/Users/pittcat/Dev/Rust/ralph-e2e/docs/plans/2026-06-20-001-feat-python-sort-algorithms-plan.md")
    if not plan.is_file():
        pytest.skip("ralph-e2e plan not on this machine")
    out = parse_plan.func(str(plan))  # type: ignore[attr-defined]
    assert len(out["units"]) == 2
    assert out["units"][0]["verification"].startswith("cd sorts")
    assert "sorts/quick_sort.py" in out["units"][0]["files"]
