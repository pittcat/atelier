"""U6 集成结构测试: case52 风格草稿 → validate → render → 报告结构锚点。

按 Plan `docs/plans/2026-07-21-002-feat-modem-report-timeline-spine-plan.md`:
  - 不调 LLM; 用合成 fixture 草稿走 spine_validate + renderer 全链路。
  - 验证 AE1 结构锚点: 领口/时间线/证据分块满足 Timeline Spine 契约。
  - 验证 analysis.json 落盘保留 spine 字段。

Driver: `uv run pytest tests/integration/test_timeline_spine_case52_structure.py`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE = ROOT / "tests" / "fixtures" / "reports" / "timeline_spine_case52_draft.json"


def _load_draft() -> dict:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def _section(md: str, name: str) -> str:
    marker = "## " + name
    after = md.split(marker, 1)[1]
    nxt = after.find("\n## ")
    if nxt == -1:
        return after
    return after[:nxt]


# ============================================================
# 全链路: validate → render → 结构断言
# ============================================================


def test_case52_draft_passes_spine_validation():
    """草稿必须通过 spine_validate (schema + spine 规则)。"""
    from modem_log_analyzer.spine_validate import validate_analysis_draft

    result = validate_analysis_draft(_load_draft())
    assert result.is_valid, f"case52 draft 应通过 spine 校验: {result.reason}"


def test_case52_rendered_report_has_timeline_spine_structure():
    """AE1 结构锚点: 渲染后报告含领口/时间线/证据分块关键结构。"""
    from modem_log_analyzer.report import render_report_md

    md = render_report_md(_load_draft())

    # 十章标题在
    for section in [
        "## 失败概览",
        "## 失败时间线",
        "## 测试步骤与日志证据",
        "## 建议行动",
    ]:
        assert section in md, f"缺章节: {section}"

    # 领口: 已确认现象 + 疑似根因 + 一行流程
    overview = _section(md, "失败概览")
    assert "外部测试 FAIL" in overview
    assert "疑似" in overview
    assert "Data 检查" in overview

    # 时间线: 非空 + 故障步标记 + ping→sms 顺序
    timeline = _section(md, "失败时间线")
    assert "无关键业务事件" not in timeline
    assert "✗" in timeline
    assert timeline.find("!ping") < timeline.find("debug_bes_rpc 4")

    # 证据分块: ping 故障步含 before/after, sms 块在
    evidence = _section(md, "测试步骤与日志证据")
    assert "ping" in evidence.lower()
    assert "sms" in evidence.lower()
    assert "故障步" in evidence
    assert "前对照" in evidence
    assert "后对照" in evidence
    assert "No response" in evidence
    assert "icmp_seq=0" in evidence
    assert "icmp_seq=1" in evidence
    # 控制脚本原文不进分块
    for forbidden in ["env_inf.py", "case_execute_action.py", "control_script.log"]:
        assert forbidden not in evidence


def test_case52_analysis_json_preserves_spine_fields():
    """analysis.json 渲染须保留 spine 字段。"""
    from modem_log_analyzer.report import render_analysis_json

    obj = json.loads(render_analysis_json(_load_draft()))
    assert obj.get("flow_one_liner")
    assert obj.get("confirmed_impact")
    assert obj.get("suspected_root_cause")
    assert obj.get("evidence_blocks")
    assert any(ev.get("is_failure_step") for ev in obj.get("timeline", []))


def test_case52_atomic_write_artifacts(tmp_path):
    """端到端: 落盘 report.md + analysis.json, 两者结构正确。"""
    from modem_log_analyzer.report import atomic_write_artifacts

    out_dir = tmp_path / "out"
    atomic_write_artifacts(
        result=_load_draft(),
        output_dir=str(out_dir),
        overwrite=False,
    )

    md = (out_dir / "report.md").read_text(encoding="utf-8")
    js = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))

    # report.md 结构
    assert "## 失败概览" in md
    assert "## 失败时间线" in md
    assert "✗" in md
    assert "No response" in md

    # analysis.json spine 字段
    assert js["flow_one_liner"]
    assert js["confirmed_impact"]
    assert js["suspected_root_cause"]
    assert js["evidence_blocks"]
    assert any(ev.get("is_failure_step") for ev in js["timeline"])


def test_case52_validate_rejects_broken_spine_variant():
    """回归保护: 破坏 spine 的草稿变体必须被拒。"""
    from modem_log_analyzer.spine_validate import validate_analysis_draft

    # 变体1: 清空 timeline
    d1 = _load_draft()
    d1["timeline"] = []
    d1["evidence_blocks"] = []
    assert not validate_analysis_draft(d1).is_valid

    # 变体2: 去掉所有 is_failure_step
    d2 = _load_draft()
    for ev in d2["timeline"]:
        ev["is_failure_step"] = False
    assert not validate_analysis_draft(d2).is_valid

    # 变体3: 控制脚本源进 evidence_blocks
    d3 = _load_draft()
    d3["evidence_refs"].append(
        {
            "ref_id": "EV-CTRL",
            "source": "control_script.log",
            "line_no": 1,
            "timestamp": None,
            "raw_text": "device:1 send cmd:!ping",
            "module": "control",
        }
    )
    d3["evidence_blocks"].append(
        {"step_label": "ping", "is_failure_step": False, "role": "main", "ref_ids": ["EV-CTRL"]}
    )
    assert not validate_analysis_draft(d3).is_valid
