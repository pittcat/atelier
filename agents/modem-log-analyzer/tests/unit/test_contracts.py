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
