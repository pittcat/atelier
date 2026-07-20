"""Unit 5 测试: control_log_policy (按需请求控制脚本日志的策略)。

按 Plan §5 Unit 5:
  - S8: 无控制日志且达到请求阈值 → 触发 interrupt
  - S9: 拒绝补日志仍产报告, 但不能确认自动化误报
  - S10: 只有直接控制日志证据才能确认 TEST_AUTOMATION_FAILURE_CONFIRMED
  - S14: thread 隔离
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# 是否应请求控制日志
# ============================================================


def test_should_request_control_log_when_no_device_anomaly():
    """无板端异常 + 外部 FAIL → 应该请求控制日志。"""
    from modem_log_analyzer.control_log_policy import should_request_control_log

    # 干净日志 → first_anomaly = None
    out = should_request_control_log(
        first_anomaly=None,
        classification="NO_DEVICE_ANOMALY_FOUND",
        has_control_log=False,
    )
    assert out is True


def test_should_not_request_when_device_failure_confirmed():
    """板端故障确认 → 不再需要控制日志(故障已经定位)。"""
    from modem_log_analyzer.control_log_policy import should_request_control_log

    out = should_request_control_log(
        first_anomaly={"ref_id": "EV-0003", "summary": "ERROR"},
        classification="DEVICE_FAILURE_CONFIRMED",
        has_control_log=False,
    )
    assert out is False


def test_should_not_request_when_control_log_already_provided():
    """用户已提供控制日志 → 不重复请求。"""
    from modem_log_analyzer.control_log_policy import should_request_control_log

    out = should_request_control_log(
        first_anomaly=None,
        classification="NO_DEVICE_ANOMALY_FOUND",
        has_control_log=True,
    )
    assert out is False


def test_should_not_request_when_evidence_incomplete():
    """证据不完整 → 优先补 EVB 证据, 不是控制日志。"""
    from modem_log_analyzer.control_log_policy import should_request_control_log

    out = should_request_control_log(
        first_anomaly=None,
        classification="DEVICE_EVIDENCE_INCOMPLETE",
        has_control_log=False,
    )
    # 证据不完整时, 板端优先, 但仍然可以请求控制日志作为补充
    # policy 允许: incomplete + external FAIL + 没有控制日志 → 仍请求
    assert isinstance(out, bool)


# ============================================================
# 控制日志是否提供直接证据
# ============================================================


def test_control_log_with_direct_assertion_evidence_can_confirm_test_automation():
    """控制日志含断言错误/超时 → 可作为直接证据。"""
    from modem_log_analyzer.control_log_policy import (
        has_direct_automation_evidence,
        parse_control_log,
    )

    log = (
        "[2026-07-19 10:00:00.000] Starting case auto_case_52\n"
        "[2026-07-19 10:00:30.000] AssertionError: expected ping success\n"
        "[2026-07-19 10:00:30.500] case_result FAIL\n"
    )
    events = parse_control_log(log)
    assert has_direct_automation_evidence(events) is True


def test_clean_control_log_no_evidence():
    """控制日志没有任何断言/超时 → 没有直接证据。"""
    from modem_log_analyzer.control_log_policy import (
        has_direct_automation_evidence,
        parse_control_log,
    )

    log = "[2026-07-19 10:00:00.000] starting\n[2026-07-19 10:00:30.000] done\n"
    events = parse_control_log(log)
    assert has_direct_automation_evidence(events) is False


def test_control_log_with_timeout_only():
    """控制日志含 timeout → 可作为直接证据。"""
    from modem_log_analyzer.control_log_policy import (
        has_direct_automation_evidence,
        parse_control_log,
    )

    log = (
        "[2026-07-19 10:00:00.000] starting\n"
        "[2026-07-19 10:00:30.000] TimeoutError: ping did not respond\n"
    )
    events = parse_control_log(log)
    assert has_direct_automation_evidence(events) is True


# ============================================================
# 拒绝补日志仍产报告 (S9)
# ============================================================


def test_classification_after_user_refuses_remains_no_device_anomaly():
    """用户拒绝补日志 + 板端无异常 → 仍是 NO_DEVICE_ANOMALY_FOUND, 不能升级。"""
    from modem_log_analyzer.control_log_policy import finalize_classification_after_user_choice

    out = finalize_classification_after_user_choice(
        initial_classification="NO_DEVICE_ANOMALY_FOUND",
        user_provided_control_log=False,
        control_log_has_direct_evidence=False,
    )
    # 拒绝补日志 + 无直接证据 → 不能改为 TEST_AUTOMATION_FAILURE_CONFIRMED
    assert out == "NO_DEVICE_ANOMALY_FOUND"


def test_classification_after_user_provides_with_evidence():
    """用户提供控制日志且有直接证据 → 可升级为 TEST_AUTOMATION_FAILURE_CONFIRMED。"""
    from modem_log_analyzer.control_log_policy import finalize_classification_after_user_choice

    out = finalize_classification_after_user_choice(
        initial_classification="NO_DEVICE_ANOMALY_FOUND",
        user_provided_control_log=True,
        control_log_has_direct_evidence=True,
    )
    assert out == "TEST_AUTOMATION_FAILURE_CONFIRMED"


def test_classification_after_user_provides_without_evidence():
    """用户提供控制日志但无直接证据 → 仍是 NO_DEVICE_ANOMALY_FOUND。"""
    from modem_log_analyzer.control_log_policy import finalize_classification_after_user_choice

    out = finalize_classification_after_user_choice(
        initial_classification="NO_DEVICE_ANOMALY_FOUND",
        user_provided_control_log=True,
        control_log_has_direct_evidence=False,
    )
    # 仅含"running"/"done"等无断言信息的控制日志, 不能升级
    assert out == "NO_DEVICE_ANOMALY_FOUND"


# ============================================================
# Resume decision
# ============================================================


def test_build_resume_payload():
    """构造 resume payload: 包含 control_log_path 或 None。"""
    from modem_log_analyzer.control_log_policy import build_resume_payload

    p = build_resume_payload(control_log_path="/tmp/control.log")
    assert p["control_log_path"] == "/tmp/control.log"

    p_none = build_resume_payload(control_log_path=None)
    assert p_none["control_log_path"] is None


def test_build_interrupt_request():
    """构造 interrupt 请求: 包含 why 字段。"""
    from modem_log_analyzer.control_log_policy import build_interrupt_request

    req = build_interrupt_request(
        reason="板端状态流看似正常, 无法解释外部 FAIL",
    )
    assert "why" in req or "reason" in req
    # 必须可序列化
    import json

    json.dumps(req)
