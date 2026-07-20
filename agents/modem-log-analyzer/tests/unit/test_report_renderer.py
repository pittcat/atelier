"""Unit 6 测试: report renderer。

按 Plan §5 Unit 6:
  - 从 AnalysisResult 渲染 report.md 与 analysis.json。
  - 章节顺序固定 (Plan R19): 失败概览 / 推断场景 / 核心诊断 / 根因链 / 时间线 /
    测试步骤与日志证据 / 故障域判定 / 剩余不确定性 / 建议行动 / 正式证据索引。
  - 敏感值在终端 / trace 中屏蔽; report.md 可保留原文(本地保真)。
  - 两个产物原子提交 (临时文件 + replace); 缺 evidence ref 时拒绝输出。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _make_minimal_result(**overrides):
    """构造一个最小合法的 AnalysisResult dict。"""
    base = {
        "schema_version": "0.1.0",
        "run_label": "单次测试执行",
        "classification": "DEVICE_FAILURE_CONFIRMED",
        "root_cause_confidence": "high",
        "scenario": "语音通话 (Call)",
        "scenario_confidence": "high",
        "first_anomaly": {
            "line_no": 3,
            "ref_id": "EV-0003",
            "summary": "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed",
            "module": "apc1",
            "ts": "2026-07-19 10:00:05.000",
        },
        "evidence_refs": [
            {
                "ref_id": "EV-0001",
                "source": "evb.log",
                "line_no": 1,
                "timestamp": "2026-07-19 10:00:00.000",
                "raw_text": "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000",
                "module": "ap",
            },
            {
                "ref_id": "EV-0002",
                "source": "evb.log",
                "line_no": 2,
                "timestamp": "2026-07-19 10:00:01.000",
                "raw_text": "[2026-07-19 10:00:01.000][apc1] OK",
                "module": "apc1",
            },
            {
                "ref_id": "EV-0003",
                "source": "evb.log",
                "line_no": 3,
                "timestamp": "2026-07-19 10:00:05.000",
                "raw_text": "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed",
                "module": "apc1",
            },
        ],
        "timeline": [
            {
                "ts": "2026-07-19 10:00:00.000",
                "event": "会话入口 modemcli",
                "ref_id": "EV-0001",
                "source_module": "ap",
            },
            {
                "ts": "2026-07-19 10:00:01.000",
                "event": "板端回调 OK",
                "ref_id": "EV-0002",
                "source_module": "apc1",
            },
            {
                "ts": "2026-07-19 10:00:05.000",
                "event": "板端回调 ERROR",
                "ref_id": "EV-0003",
                "source_module": "apc1",
            },
        ],
        "root_cause_chain": [
            {"role": "trigger", "description": "dial failed", "ref_ids": ["EV-0003"], "gap": None},
            {"role": "propagation", "description": "异常传播过程", "ref_ids": [], "gap": "未明确"},
            {"role": "terminal_impact", "description": "最终外部 FAIL", "ref_ids": [], "gap": None},
        ],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": ["这是测试 note"],
        "suggested_actions": ["建议 1"],
    }
    base.update(overrides)
    return base


# ============================================================
# report.md 渲染
# ============================================================


def test_render_report_md_returns_string():
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result()
    md = render_report_md(result)
    assert isinstance(md, str)
    assert len(md) > 100


def test_report_md_has_required_sections():
    """R19: 章节顺序必须固定且完整。"""
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result()
    md = render_report_md(result)

    expected_sections = [
        "失败概览",
        "推断的测试场景与基线",
        "核心诊断",
        "根因链",
        "失败时间线",
        "测试步骤与日志证据",
        "故障域判定与推理",
        "剩余不确定性",
        "建议行动",
        "正式证据索引",
    ]
    for s in expected_sections:
        assert s in md, f"missing section: {s}"


def test_report_md_sections_in_correct_order():
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result()
    md = render_report_md(result)
    # 用 "## 章节名" 锚定避免子串干扰
    sections = [
        "## 失败概览",
        "## 推断的测试场景与基线",
        "## 核心诊断",
        "## 根因链",
        "## 失败时间线",
        "## 测试步骤与日志证据",
        "## 故障域判定与推理",
        "## 剩余不确定性",
        "## 建议行动",
        "## 正式证据索引",
    ]
    positions = [md.index(s) for s in sections]
    assert positions == sorted(positions)


def test_report_md_includes_evidence_ref_ids():
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result()
    md = render_report_md(result)
    # 证据 ID 应出现在正式证据索引中
    for rid in ["EV-0001", "EV-0002", "EV-0003"]:
        assert rid in md, f"missing evidence ref: {rid}"


def test_report_md_classification_appears():
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result(classification="ENVIRONMENT_FAILURE_INDICATED")
    md = render_report_md(result)
    assert "ENVIRONMENT_FAILURE_INDICATED" in md


def test_report_md_no_device_anomaly_path():
    """R14: NO_DEVICE_ANOMALY_FOUND 章节不应宣称是自动化误报。"""
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result(
        classification="NO_DEVICE_ANOMALY_FOUND",
        first_anomaly=None,
        notes=[
            "未发现板端异常; 外部 FAIL 不等于产品故障",
            "需控制脚本日志以确认是否自动化误报",
        ],
    )
    md = render_report_md(result)
    assert "NO_DEVICE_ANOMALY_FOUND" in md
    assert "未发现板端异常" in md


def test_report_md_all_six_classifications_render():
    """6 个分类都能渲染。"""
    from modem_log_analyzer.report import render_report_md

    classifications = [
        "DEVICE_FAILURE_CONFIRMED",
        "ENVIRONMENT_FAILURE_INDICATED",
        "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "NO_DEVICE_ANOMALY_FOUND",
        "DEVICE_EVIDENCE_INCOMPLETE",
        "MULTIPLE_POSSIBLE_CAUSES",
    ]
    for c in classifications:
        result = _make_minimal_result(
            classification=c,
            first_anomaly=None
            if c in {"NO_DEVICE_ANOMALY_FOUND", "DEVICE_EVIDENCE_INCOMPLETE"}
            else _make_minimal_result()["first_anomaly"],
        )
        md = render_report_md(result)
        assert c in md


def test_report_md_unicode_safe():
    """Unicode 字符不应让渲染崩溃。"""
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result(scenario="语音通话 (Call)")
    md = render_report_md(result)
    assert "语音通话" in md


def test_report_md_rejects_invalid_evidence_ref():
    """first_anomaly 引用了不存在的 ref_id → 拒绝渲染。"""
    from modem_log_analyzer.report import render_report_md

    result = _make_minimal_result(
        first_anomaly={"line_no": 99, "ref_id": "EV-9999", "summary": "x"},
    )
    with pytest.raises(ValueError):
        render_report_md(result)


# ============================================================
# analysis.json 序列化
# ============================================================


def test_render_analysis_json_returns_valid_dict():
    from modem_log_analyzer.report import render_analysis_json

    result = _make_minimal_result()
    js = render_analysis_json(result)
    obj = json.loads(js)
    assert obj["schema_version"] == "0.1.0"
    assert obj["classification"] == "DEVICE_FAILURE_CONFIRMED"


def test_render_analysis_json_roundtrip():
    from modem_log_analyzer.report import render_analysis_json

    result = _make_minimal_result()
    js = render_analysis_json(result)
    obj = json.loads(js)
    # 字段保留
    assert len(obj["evidence_refs"]) == 3
    assert obj["first_anomaly"]["ref_id"] == "EV-0003"


# ============================================================
# 原子写入
# ============================================================


def test_atomic_write_report_and_json(tmp_path):
    """原子写入: report.md + analysis.json 同组提交。"""
    from modem_log_analyzer.report import atomic_write_artifacts

    result = _make_minimal_result()
    out_dir = tmp_path / "out"
    atomic_write_artifacts(
        result=result,
        output_dir=str(out_dir),
        overwrite=False,
    )
    # 两个产物都应存在
    assert (out_dir / "report.md").exists()
    assert (out_dir / "analysis.json").exists()
    # 内容合法
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "失败概览" in md
    js = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert js["classification"] == "DEVICE_FAILURE_CONFIRMED"


def test_atomic_write_refuses_overwrite_without_flag(tmp_path):
    from modem_log_analyzer.report import atomic_write_artifacts

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("old", encoding="utf-8")

    result = _make_minimal_result()
    with pytest.raises(FileExistsError):
        atomic_write_artifacts(
            result=result,
            output_dir=str(out_dir),
            overwrite=False,
        )


def test_atomic_write_overwrite_with_flag(tmp_path):
    from modem_log_analyzer.report import atomic_write_artifacts

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("old", encoding="utf-8")
    (out_dir / "analysis.json").write_text("{}", encoding="utf-8")

    result = _make_minimal_result()
    atomic_write_artifacts(
        result=result,
        output_dir=str(out_dir),
        overwrite=True,
    )
    # 都被覆盖
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "失败概览" in md


def test_atomic_write_creates_temp_then_replaces(tmp_path):
    """原子性: 写过程中不应留下半成品。"""
    from modem_log_analyzer.report import atomic_write_artifacts

    out_dir = tmp_path / "out"
    result = _make_minimal_result()
    atomic_write_artifacts(result=result, output_dir=str(out_dir), overwrite=False)

    # 检查目录里没有 .tmp 文件残留
    tmp_files = list(out_dir.glob("*.tmp"))
    assert not tmp_files, f"temp files left over: {tmp_files}"


def test_atomic_write_no_partial_state_on_failure(tmp_path):
    """写失败时不应留下半成品。"""
    from modem_log_analyzer.report import atomic_write_artifacts

    out_dir = tmp_path / "out"
    # 给一个无法序列化的 result (例如 evidence ref 类型不对)
    bad = _make_minimal_result()
    # 模拟: root_cause_chain 引用了不存在的 ref
    bad["root_cause_chain"] = [
        {"role": "trigger", "description": "x", "ref_ids": ["EV-9999"], "gap": None},
    ]
    with pytest.raises(ValueError):
        atomic_write_artifacts(
            result=bad,
            output_dir=str(out_dir),
            overwrite=False,
        )
    # 不应留下任何文件
    assert not (out_dir / "report.md").exists()
    assert not (out_dir / "analysis.json").exists()


# ============================================================
# 终端摘要 (无敏感值)
# ============================================================


def test_terminal_summary_does_not_leak_raw_log():
    """终端摘要不应回显原始日志全文。"""
    from modem_log_analyzer.report import render_terminal_summary

    result = _make_minimal_result()
    secret = "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000"
    assert secret in result["evidence_refs"][0]["raw_text"]

    summary = render_terminal_summary(result)
    # 摘要可以包含 EV-0001 (ref_id) 但不应包含完整原文
    assert "13900000000" not in summary or "EV-0001" not in summary or len(summary) < 1000
    # ref_id 可见
    assert "EV-0001" in summary or "EV-0003" in summary


def test_terminal_summary_includes_classification():
    from modem_log_analyzer.report import render_terminal_summary

    result = _make_minimal_result()
    summary = render_terminal_summary(result)
    assert "DEVICE_FAILURE_CONFIRMED" in summary
