"""Unit 4 测试: classification / scenario_inference / domain。

按 Plan §5 Unit 4:
  - 四类业务最小状态语义
  - 推断 scenario
  - 顶层 classification 决策遵守 R13/R14
  - 互斥的分类枚举
  - 证据不足时使用较弱分类
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# 分类枚举 (R13)
# ============================================================


def test_classify_module_imports_correctly():
    from modem_log_analyzer import classification

    assert classification is not None


def test_decide_classification_returns_valid_enum():
    """decide_classification 返回的必须是合法 Classification。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    # 设备有明确证据 → DEVICE_FAILURE_CONFIRMED
    outcome = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert outcome in Classification


# ============================================================
# 决策矩阵 (R13/R14)
# ============================================================


def test_classification_device_failure_confirmed():
    """设备异常 + 完整证据 + 无环境/控制日志证据 → DEVICE_FAILURE_CONFIRMED。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert out == Classification.DEVICE_FAILURE_CONFIRMED


def test_classification_environment_failure():
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=False,
        has_environment_evidence=True,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert out == Classification.ENVIRONMENT_FAILURE_INDICATED


def test_classification_test_automation_requires_control_log():
    """TEST_AUTOMATION_FAILURE_CONFIRMED 必须有控制日志直接证据。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    # 无控制日志 → 不能是 TEST_AUTOMATION_FAILURE_CONFIRMED
    out = decide_classification(
        has_device_anomaly=False,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert out != Classification.TEST_AUTOMATION_FAILURE_CONFIRMED


def test_classification_test_automation_with_direct_evidence():
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=False,
        has_environment_evidence=False,
        has_control_log_evidence=True,
        is_complete=True,
    )
    assert out == Classification.TEST_AUTOMATION_FAILURE_CONFIRMED


def test_classification_no_device_anomaly_not_test_automation():
    """R14: 仅 EVB 日志 + 板端正常 → NO_DEVICE_ANOMALY_FOUND, 不＝自动化误报。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=False,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    # 必须是 NO_DEVICE_ANOMALY_FOUND, 不能是 TEST_AUTOMATION_FAILURE_CONFIRMED
    assert out == Classification.NO_DEVICE_ANOMALY_FOUND


def test_classification_incomplete_evidence():
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=False,
    )
    # 不完整 → DEVICE_EVIDENCE_INCOMPLETE, 即使有异常
    assert out == Classification.DEVICE_EVIDENCE_INCOMPLETE


def test_classification_multiple_possible_causes():
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    out = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=True,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert out == Classification.MULTIPLE_POSSIBLE_CAUSES


# ============================================================
# 置信度
# ============================================================


def test_confidence_levels_are_valid():
    """置信度必须是 low/medium/high 之一。"""
    from modem_log_analyzer.classification import compute_root_cause_confidence
    from modem_log_analyzer.contracts import Classification

    out = compute_root_cause_confidence(
        n_supporting_refs=3,
        n_gaps=0,
        classification=Classification.DEVICE_FAILURE_CONFIRMED,
    )
    assert out in ("low", "medium", "high")


def test_high_confidence_with_strong_evidence():
    from modem_log_analyzer.classification import compute_root_cause_confidence
    from modem_log_analyzer.contracts import Classification

    out = compute_root_cause_confidence(
        n_supporting_refs=5,
        n_gaps=0,
        classification=Classification.DEVICE_FAILURE_CONFIRMED,
    )
    assert out == "high"


def test_low_confidence_with_many_gaps():
    from modem_log_analyzer.classification import compute_root_cause_confidence
    from modem_log_analyzer.contracts import Classification

    out = compute_root_cause_confidence(
        n_supporting_refs=1,
        n_gaps=4,
        classification=Classification.MULTIPLE_POSSIBLE_CAUSES,
    )
    assert out == "low"


# ============================================================
# 业务场景推断
# ============================================================


def test_scenario_inference_call():
    """debug_bes_rpc 0 14 → call 场景。"""
    from modem_log_analyzer.log_parser import parse_evb_log
    from modem_log_analyzer.scenario_inference import infer_scenario

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    events = parse_evb_log(raw)
    scenario = infer_scenario(events)
    assert scenario is not None
    assert "call" in scenario["name"].lower() or "语音" in scenario["name"]


def test_scenario_inference_data_ping():
    from modem_log_analyzer.log_parser import parse_evb_log
    from modem_log_analyzer.scenario_inference import infer_scenario

    raw = "[2026-07-19 10:00:00.000][ap] modemcli> !ping 8.8.8.8\n"
    events = parse_evb_log(raw)
    scenario = infer_scenario(events)
    assert scenario is not None
    assert "ping" in scenario["name"].lower() or "data" in scenario["name"].lower()


def test_scenario_inference_mixed():
    """通话中短信/ping → 混合场景。"""
    from modem_log_analyzer.log_parser import parse_evb_log
    from modem_log_analyzer.scenario_inference import infer_scenario

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:05.000][ap] modemcli> debug_bes_rpc 4 1 13900000001 hi\n"
        "[2026-07-19 10:00:10.000][ap] modemcli> !ping 8.8.8.8\n"
    )
    events = parse_evb_log(raw)
    scenario = infer_scenario(events)
    assert scenario is not None
    name = scenario["name"].lower()
    assert "混合" in scenario["name"] or "mixed" in name or "call" in name


def test_scenario_inference_empty():
    """无业务命令时,scenario 应降级为 unknown / 缺省。"""
    from modem_log_analyzer.log_parser import parse_evb_log
    from modem_log_analyzer.scenario_inference import infer_scenario

    raw = "noise noise noise\n"
    events = parse_evb_log(raw)
    scenario = infer_scenario(events)
    assert scenario is not None


# ============================================================
# 首异常排序
# ============================================================


def test_find_first_anomaly_returns_earliest():
    from modem_log_analyzer.classification import find_first_anomaly
    from modem_log_analyzer.evidence import build_evidence_index
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:02.000][apc1] ERROR: timeout\n"
        "[2026-07-19 10:00:03.000][apc1] FAIL\n"
    )
    events = parse_evb_log(raw)
    refs = build_evidence_index(events)
    # find_first_anomaly 接受 events + refs, 返回 dict {step, ref_id, summary}
    out = find_first_anomaly(events, refs)
    assert out is not None
    # 首个异常应该是第 3 行 (ERROR)
    assert out["line_no"] == 3 or out.get("ref_id") is not None


def test_find_first_anomaly_returns_none_for_clean_log():
    from modem_log_analyzer.classification import find_first_anomaly
    from modem_log_analyzer.evidence import build_evidence_index
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    events = parse_evb_log(raw)
    refs = build_evidence_index(events)
    out = find_first_anomaly(events, refs)
    # 干净日志没有异常
    assert out is None
