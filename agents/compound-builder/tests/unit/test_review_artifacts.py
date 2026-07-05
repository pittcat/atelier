"""review_artifacts + review_synthesizer 落盘测试。"""
from __future__ import annotations

from compound_builder.nodes.review_synthesizer import review_synthesizer
from compound_builder.review_artifacts import write_review_report_md
from compound_builder.state import Finding


def test_write_review_report_md(tmp_path):
    findings: list[Finding] = [
        {
            "dimension": "testing",
            "severity": "p2",
            "file": "sorts/tests/test_foo.py",
            "line": 10,
            "summary": "Missing edge case for empty input.",
            "suggested_fix": "Add parametrized empty test.",
        },
    ]
    path = write_review_report_md(
        tmp_path,
        1,
        plan={"title": "demo", "acceptance": ["R1"], "scope_boundaries": []},
        units=[{"id": "step-01", "title": "u1", "status": "passed"}],
        findings=findings,
        fix_plan_path="null",
    )
    text = path.read_text(encoding="utf-8")
    assert path.name == "review-report.md"
    assert "Round 1" in text
    assert "testing" in text
    assert "Missing edge case" in text


def test_synthesizer_writes_artifacts_even_with_zero_findings(tmp_path):
    state = {
        "workdir": str(tmp_path),
        "review_round": 1,
        "review_findings": [],
        "plan": {"title": "t", "acceptance": [], "scope_boundaries": []},
        "units": [{"id": "step-01", "title": "u1", "status": "passed"}],
        "decisions": [],
        "results_log": [],
    }
    out = review_synthesizer(state)
    assert out["fix_plan_path"] == "null"
    report = tmp_path / ".compound_builder" / "review_rounds" / "r01" / "review-report.md"
    findings_json = tmp_path / ".compound_builder" / "review_rounds" / "r01" / "review-findings.json"
    assert report.is_file()
    assert findings_json.is_file()
    assert out["review_report_path"] == str(report)


def test_synthesizer_writes_fix_plan_on_p0(tmp_path):
    state = {
        "workdir": str(tmp_path),
        "review_round": 1,
        "review_findings": [
            {
                "dimension": "correctness",
                "severity": "p0",
                "file": "sorts/foo.py",
                "summary": "Critical bug",
                "suggested_fix": "Fix off-by-one",
            },
        ],
        "plan": {"title": "t", "acceptance": [], "scope_boundaries": []},
        "units": [],
        "decisions": [],
        "results_log": [],
    }
    out = review_synthesizer(state)
    fix_plan = tmp_path / ".compound_builder" / "review_rounds" / "r01" / "fix-plan.json"
    assert fix_plan.is_file()
    assert out["fix_plan_path"] == str(fix_plan)
    assert len(out.get("fix_units") or []) == 1
