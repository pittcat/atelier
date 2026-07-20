"""Unit 5 集成测试: interrupt + resume + thread 隔离 (S8/S9/S10/S14)。

按 Plan §5 Unit 5:
  - S8: 干净日志 + 外部 FAIL → interrupt 触发, CLI 应能 resume
  - S9: 拒绝补日志 → 仍产报告, 分类保持 NO_DEVICE_ANOMALY_FOUND
  - S10: 提供含直接证据的控制日志 → 可升级为 TEST_AUTOMATION_FAILURE_CONFIRMED
  - S14: thread A resume 不影响 thread B
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _make_evb(tmp_path: Path, content: str) -> str:
    p = tmp_path / "evb.log"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_control(tmp_path: Path, content: str) -> str:
    p = tmp_path / "control.log"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ============================================================
# S8: 干净日志 + 外部 FAIL → interrupt 触发
# ============================================================


def test_interrupt_request_triggered_when_no_anomaly(tmp_path):
    """板端无异常 → 触发 interrupt 请求控制日志。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    # interrupt_request 应被生成
    ir = result["_meta"].get("interrupt_request")
    assert ir is not None
    assert ir["type"] == "REQUEST_CONTROL_LOG"
    assert "why" in ir


def test_no_interrupt_when_device_failure_confirmed(tmp_path):
    """板端故障已确认 → 不需要 interrupt。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed\n"
    )
    log = _make_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        overwrite=False,
        dry_run=True,
    )
    ir = result["_meta"].get("interrupt_request")
    assert ir is None


# ============================================================
# S9: 拒绝补日志 → 仍产报告
# ============================================================


def test_refuse_control_log_keeps_no_device_anomaly(tmp_path):
    """干净日志 + 拒绝补控制日志 → 仍是 NO_DEVICE_ANOMALY_FOUND。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        control_log_path=None,  # 用户拒绝
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "NO_DEVICE_ANOMALY_FOUND"
    # 不能是 TEST_AUTOMATION_FAILURE_CONFIRMED
    assert result["classification"] != "TEST_AUTOMATION_FAILURE_CONFIRMED"


# ============================================================
# S10: 提供直接证据 → 升级为 TEST_AUTOMATION_FAILURE_CONFIRMED
# ============================================================


def test_direct_evidence_in_control_log_promotes_classification(tmp_path):
    """控制日志含 AssertionError → 可升级。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb(tmp_path, raw)

    control = (
        "[2026-07-19 10:00:00.000] starting case auto_case_52\n"
        "[2026-07-19 10:00:30.000] AssertionError: expected ping success\n"
    )
    cp = _make_control(tmp_path, control)

    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        control_log_path=cp,
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "TEST_AUTOMATION_FAILURE_CONFIRMED"
    assert result["control_log_used"] is True


def test_control_log_without_direct_evidence_keeps_classification(tmp_path):
    """控制日志无直接证据 → 保持 NO_DEVICE_ANOMALY_FOUND。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb(tmp_path, raw)
    control = "[2026-07-19 10:00:00.000] starting\n[2026-07-19 10:00:30.000] done\n"
    cp = _make_control(tmp_path, control)

    out_dir = tmp_path / "out"
    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        control_log_path=cp,
        overwrite=False,
        dry_run=True,
    )
    assert result["classification"] == "NO_DEVICE_ANOMALY_FOUND"


# ============================================================
# S14: thread 隔离
# ============================================================


def test_thread_isolation_different_results(tmp_path):
    """两个 thread 跑同一份 EVB 日志: 各自 result 独立。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _make_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    control = "[2026-07-19 10:00:00.000] starting\n[2026-07-19 10:00:30.000] done\n"
    cp = _make_control(tmp_path, control)

    svc = AnalysisService()
    r1 = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        thread_id="thread-A",
        overwrite=False,
        dry_run=True,
    )
    r2 = svc.run_analyze(
        evb_log_path=log,
        output_dir=str(out_dir),
        thread_id="thread-B",
        control_log_path=cp,  # thread-B 提供 control
        overwrite=False,
        dry_run=True,
    )
    # metadata 应记录不同 thread_id
    assert r1["_meta"]["thread_id"] == "thread-A"
    assert r2["_meta"]["thread_id"] == "thread-B"
    # 两者 evidence_refs 应该完全一致 (输入相同)
    ids1 = sorted(e["ref_id"] for e in r1["evidence_refs"])
    ids2 = sorted(e["ref_id"] for e in r2["evidence_refs"])
    assert ids1 == ids2
    # 但 control_log_used 不同
    assert r1["control_log_used"] is False
    assert r2["control_log_used"] is True


# ============================================================
# Resume protocol
# ============================================================


def test_resume_protocol_build():
    """build_resume_payload 返回稳定结构。"""
    from modem_log_analyzer.control_log_policy import build_resume_payload

    p1 = build_resume_payload(control_log_path="/tmp/x.log")
    assert p1 == {"control_log_path": "/tmp/x.log"}

    p2 = build_resume_payload(control_log_path=None)
    assert p2 == {"control_log_path": None}
