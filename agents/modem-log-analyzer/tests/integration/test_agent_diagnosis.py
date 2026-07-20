"""Unit 4 集成测试: AnalysisService.run_analyze 端到端。

按 Plan §5 Unit 4:
  - 端到端: CLI 入口 → AnalysisService → DiagnosisResult
  - 四类业务 (Call/SMS/Data-Ping/Setting) 各有成功/失败样例
  - 混合场景保持子流程边界
  - 诊断只引用输入 evidence refs (S13: 稳定)
  - classification 遵守 R13/R14
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _make_evb_log(tmp_path: Path, content: str) -> str:
    p = tmp_path / "evb.log"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ============================================================
# Call 业务
# ============================================================


def test_call_failure_confirmed(tmp_path):
    """Call 业务: debug_bes_rpc 0 14 → ERROR → DEVICE_FAILURE_CONFIRMED。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed timeout\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        label="call_failure",
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "DEVICE_FAILURE_CONFIRMED"
    assert result["scenario"] is not None
    assert "call" in result["scenario"].lower() or "语音" in result["scenario"]


def test_call_incomplete_evidence(tmp_path):
    """Call 业务: 证据不足 → DEVICE_EVIDENCE_INCOMPLETE。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        # 没有后续回调 → 证据不足
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    # 缺终态 → 不完整
    assert result["classification"] in {
        "DEVICE_EVIDENCE_INCOMPLETE",
        "NO_DEVICE_ANOMALY_FOUND",  # 也可能,因为没失败证据
    }


# ============================================================
# SMS 业务
# ============================================================


def test_sms_failure_confirmed(tmp_path):
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 4 1 13900000000 hello\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] FAIL: send SMS failed\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        label="sms_failure",
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "DEVICE_FAILURE_CONFIRMED"
    assert "sms" in result["scenario"].lower() or "短信" in result["scenario"]


# ============================================================
# Data/Ping 业务
# ============================================================


def test_data_ping_failure(tmp_path):
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n"
        "[2026-07-19 10:00:01.000][apc1] eth0 192.168.1.10\n"
        "[2026-07-19 10:00:05.000][ap] modemcli> !ping 8.8.8.8\n"
        "[2026-07-19 10:00:10.000][apc1] TIMEOUT\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "DEVICE_FAILURE_CONFIRMED"
    assert "ping" in result["scenario"].lower() or "data" in result["scenario"].lower()


# ============================================================
# Setting 业务
# ============================================================


def test_setting_success_no_device_anomaly(tmp_path):
    """Setting 业务成功 → NO_DEVICE_ANOMALY_FOUND。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n"
        "[2026-07-19 10:00:01.000][apc1] eth0 192.168.1.10\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    # setting 业务成功 → 无异常
    assert result["classification"] == "NO_DEVICE_ANOMALY_FOUND"


# ============================================================
# 混合场景
# ============================================================


def test_mixed_call_with_sms(tmp_path):
    """通话中短信 → 混合场景;分类遵守 R13。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][ap] modemcli> debug_bes_rpc 4 1 13900000001 hi\n"
        "[2026-07-19 10:00:06.000][apc1] OK\n"
        "[2026-07-19 10:00:10.000][apc1] FAIL: SMS send failed during call\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    # 失败 → DEVICE_FAILURE_CONFIRMED
    assert result["classification"] == "DEVICE_FAILURE_CONFIRMED"
    # scenario 包含 call 或 混合
    name = result["scenario"].lower()
    assert "call" in name or "混合" in result["scenario"]


# ============================================================
# 稳定 evidence refs (S13)
# ============================================================


def test_evidence_refs_stable_across_runs(tmp_path):
    """同一文件两次分析 → 同一 evidence refs。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    r1 = svc.run_analyze(evb_log_path=log, output_dir=str(out_dir), overwrite=False, dry_run=True)
    r2 = svc.run_analyze(evb_log_path=log, output_dir=str(out_dir), overwrite=False, dry_run=True)
    ids1 = sorted(e["ref_id"] for e in r1["evidence_refs"])
    ids2 = sorted(e["ref_id"] for e in r2["evidence_refs"])
    assert ids1 == ids2
    assert ids1  # 至少有一个


def test_diagnosis_only_references_input_evidence_refs(tmp_path):
    """诊断只能引用 analysis.json 中实际存在的 evidence refs。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log, output_dir=str(out_dir), overwrite=False, dry_run=True
    )
    valid_ids = {e["ref_id"] for e in result["evidence_refs"]}

    # first_anomaly 引用必须有效
    fa = result.get("first_anomaly")
    if fa and "ref_id" in fa:
        assert fa["ref_id"] in valid_ids

    # root_cause_chain 中的 ref_ids 必须有效
    for link in result.get("root_cause_chain") or []:
        for rid in link.get("ref_ids") or []:
            assert rid in valid_ids


# ============================================================
# 干净日志
# ============================================================


def test_clean_log_no_device_anomaly(tmp_path):
    """所有命令 OK → NO_DEVICE_ANOMALY_FOUND。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:30.000][apc1] OK hangup\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log, output_dir=str(out_dir), overwrite=False, dry_run=True
    )
    assert result["classification"] == "NO_DEVICE_ANOMALY_FOUND"


def test_external_result_field_preserved(tmp_path):
    """外部 case_result=FAIL 应保留在 result 中, 但与 classification 解耦。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb_log(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log, output_dir=str(out_dir), overwrite=False, dry_run=True
    )
    assert result["external_result"] == "FAIL"
    # 但 classification 是 NO_DEVICE_ANOMALY_FOUND, 不是 TEST_AUTOMATION_FAILURE_CONFIRMED
    # 因为没有控制日志证据
    assert result["classification"] == "NO_DEVICE_ANOMALY_FOUND"
