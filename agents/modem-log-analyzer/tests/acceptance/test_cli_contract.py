"""modem-log-analyzer —— CLI 公共契约验收测试 (Unit 1)。

锁定:
  - CLI 顶层只声明 ``analyze`` 命令
  - ``analyze`` 不要求 loop/case 标识
  - analysis.json 的诊断枚举合法集（顶层诊断分类的金标准枚举）
  - JSON schema 版本号
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """直接调 Python -m 运行 cli（不依赖 console script 装包）。"""
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = "test-no-key"
    env["MODEM_LOG_ANALYZER_QUIET"] = "true"
    # 把测试的 src/ 和 libs/common/src 传过去
    py_path = ROOT / "src"
    lib_src = ROOT.parent.parent / "libs" / "common" / "src"
    env["PYTHONPATH"] = f"{py_path}:{lib_src}"
    return subprocess.run(
        [sys.executable, "-m", "modem_log_analyzer.cli", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )


def test_cli_help_works():
    """``modem-log-analyzer --help`` 必须能跑,只声明真实支持的 analyze 命令。"""
    proc = _run_cli("--help")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "analyze" in proc.stdout, "help 必须声明 analyze 命令"
    for fake in ("train", "replay-thread", "open-stream"):
        assert fake not in proc.stdout, f"help 不应包含虚构命令 {fake}"


def test_analyze_help_does_not_require_loop():
    """``analyze --help`` 不应要求 loop/case 标识。"""
    proc = _run_cli("analyze", "--help")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    out = proc.stdout
    assert "--loop" not in out, "analyze 不应声明 --loop 参数"
    assert "--evb-log" in out
    assert "--output" in out


ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "DEVICE_FAILURE_CONFIRMED",
        "ENVIRONMENT_FAILURE_INDICATED",
        "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "NO_DEVICE_ANOMALY_FOUND",
        "DEVICE_EVIDENCE_INCOMPLETE",
        "MULTIPLE_POSSIBLE_CAUSES",
    }
)


def test_classification_enum_matches_plan_r13():
    """R13: 6 个分类必须与需求 R13 完全一致。"""
    from modem_log_analyzer.contracts import Classification

    actual = {c.value for c in Classification}
    assert actual == ALLOWED_CLASSIFICATIONS


def test_analysis_schema_version_is_explicit():
    """schema 必须有版本字段。"""
    from modem_log_analyzer.contracts import (
        ANALYSIS_SCHEMA_VERSION,
        AnalysisResult,
    )

    assert isinstance(ANALYSIS_SCHEMA_VERSION, str)
    assert ANALYSIS_SCHEMA_VERSION  # 非空
    fields = AnalysisResult.model_fields
    assert "schema_version" in fields


def test_analysis_json_round_trip():
    """最小合法 AnalysisResult 可以序列化/反序列化。"""
    from modem_log_analyzer.contracts import (
        AnalysisResult,
        Classification,
    )

    minimal = AnalysisResult(
        schema_version="0.1.0",
        run_label="单次测试执行",
        classification=Classification.NO_DEVICE_ANOMALY_FOUND,
        root_cause_confidence="low",
        evidence_refs=[],
        root_cause_chain=[],
        timeline=[],
    )
    js = minimal.model_dump_json()
    obj = json.loads(js)
    assert obj["schema_version"] == "0.1.0"
    assert obj["classification"] == "NO_DEVICE_ANOMALY_FOUND"


def test_unknown_classification_is_rejected():
    """非法分类必须被 schema 拒绝。"""
    from pydantic import ValidationError

    from modem_log_analyzer.contracts import AnalysisResult

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(
            {
                "schema_version": "0.1.0",
                "run_label": "x",
                "classification": "WHATEVER_NOT_A_VALID_CLASS",
                "root_cause_confidence": "low",
                "evidence_refs": [],
                "root_cause_chain": [],
                "timeline": [],
            }
        )
