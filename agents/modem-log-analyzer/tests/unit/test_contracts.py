"""Unit 1: contracts.py 的 Pydantic 模型必须接受最小合法输入,拒绝非法分类。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _import_contracts():
    from modem_log_analyzer import contracts

    return contracts


def test_schema_version_constant_exists():
    c = _import_contracts()
    assert hasattr(c, "ANALYSIS_SCHEMA_VERSION")
    assert isinstance(c.ANALYSIS_SCHEMA_VERSION, str)
    assert c.ANALYSIS_SCHEMA_VERSION  # 非空


def test_classification_enum_exists():
    c = _import_contracts()
    assert hasattr(c, "Classification")
    values = {member.value for member in c.Classification}
    expected = {
        "DEVICE_FAILURE_CONFIRMED",
        "ENVIRONMENT_FAILURE_INDICATED",
        "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "NO_DEVICE_ANOMALY_FOUND",
        "DEVICE_EVIDENCE_INCOMPLETE",
        "MULTIPLE_POSSIBLE_CAUSES",
    }
    assert values == expected


def test_analysis_result_minimal_accept():
    """最小合法输入可以被构造。"""
    c = _import_contracts()
    r = c.AnalysisResult(
        schema_version=c.ANALYSIS_SCHEMA_VERSION,
        run_label="单次测试执行",
        classification=c.Classification.NO_DEVICE_ANOMALY_FOUND,
        root_cause_confidence="low",
        evidence_refs=[],
        root_cause_chain=[],
        timeline=[],
    )
    assert r.classification == c.Classification.NO_DEVICE_ANOMALY_FOUND


def test_analysis_result_rejects_invalid_classification():
    from pydantic import ValidationError

    c = _import_contracts()
    bad: dict[str, Any] = {
        "schema_version": c.ANALYSIS_SCHEMA_VERSION,
        "run_label": "x",
        "classification": "DEFINTELY_NOT_A_VALID_VALUE",
        "root_cause_confidence": "low",
        "evidence_refs": [],
        "root_cause_chain": [],
        "timeline": [],
    }
    with pytest.raises(ValidationError):
        c.AnalysisResult.model_validate(bad)


def test_run_request_accepts_minimal_valid_input():
    """CLI 入口接受的最小合法请求。"""
    c = _import_contracts()
    req = c.RunRequest(evb_log_path="/tmp/x.log", output_dir="/tmp/out")
    assert req.evb_log_path == "/tmp/x.log"
    assert req.output_dir == "/tmp/out"
    # 可选字段默认值
    assert req.control_log_path is None
    assert req.label is None
    assert req.overwrite is False
    assert req.thread_id is None


# ============================================================
# Timeline Spine 字段 (Plan 2026-07-21-002 / U2)
# ============================================================


def test_timeline_event_optional_spine_fields_default():
    """TimelineEvent 新增 spine 字段缺省值兼容旧最小结果。"""
    c = _import_contracts()
    ev = c.TimelineEvent(event="x", ref_id="EV-1")
    assert ev.is_failure_step is False
    assert ev.step_label is None
    assert ev.kind is None


def test_timeline_event_accepts_spine_fields():
    c = _import_contracts()
    ev = c.TimelineEvent(
        event="首包超时",
        ref_id="EV-2",
        kind="failure",
        step_label="ping",
        is_failure_step=True,
    )
    assert ev.is_failure_step is True
    assert ev.kind == "failure"
    assert ev.step_label == "ping"


def test_evidence_block_minimal():
    c = _import_contracts()
    b = c.EvidenceBlock(step_label="ping")
    assert b.step_label == "ping"
    assert b.is_failure_step is False
    assert b.role == "main"
    assert b.ref_ids == []


def test_analysis_result_accepts_spine_fields():
    """AnalysisResult 接受 spine 字段; 旧最小结果仍兼容。"""
    c = _import_contracts()
    r = c.AnalysisResult(
        schema_version=c.ANALYSIS_SCHEMA_VERSION,
        classification=c.Classification.DEVICE_EVIDENCE_INCOMPLETE,
        root_cause_confidence="low",
        flow_one_liner="Data 检查 -> ping -> SMS",
        confirmed_impact="外部 FAIL: ping 首包超时",
        suspected_root_cause="疑似 DNS 延迟",
        timeline=[
            c.TimelineEvent(
                event="首包超时",
                ref_id="EV-1",
                kind="failure",
                step_label="ping",
                is_failure_step=True,
            )
        ],
        evidence_blocks=[
            c.EvidenceBlock(step_label="ping", is_failure_step=True, role="main", ref_ids=["EV-1"]),
        ],
    )
    assert r.flow_one_liner == "Data 检查 -> ping -> SMS"
    assert r.confirmed_impact is not None
    assert r.suspected_root_cause is not None
    assert r.evidence_blocks[0].is_failure_step is True
    assert r.timeline[0].is_failure_step is True


def test_analysis_result_rejects_unknown_spine_field():
    """extra=forbid 仍然生效: 未知字段被拒。"""
    from pydantic import ValidationError

    c = _import_contracts()
    bad: dict[str, Any] = {
        "schema_version": c.ANALYSIS_SCHEMA_VERSION,
        "classification": "DEVICE_EVIDENCE_INCOMPLETE",
        "root_cause_confidence": "low",
        "not_a_real_field": 1,
    }
    with pytest.raises(ValidationError):
        c.AnalysisResult.model_validate(bad)


def test_fixture_case52_draft_validates():
    """U1 case52 fixture 必须可被 AnalysisResult.model_validate 接受。"""
    import json

    c = _import_contracts()
    fixture = ROOT / "tests" / "fixtures" / "reports" / "timeline_spine_case52_draft.json"
    with fixture.open(encoding="utf-8") as f:
        data = json.load(f)
    r = c.AnalysisResult.model_validate(data)
    assert r.flow_one_liner is not None
    assert r.confirmed_impact is not None
    assert r.suspected_root_cause is not None
    assert any(ev.is_failure_step for ev in r.timeline)
    assert r.evidence_blocks
