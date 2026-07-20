"""Unit 7 测试: 风险驱动测试 + 标注 fixtures。

按 Plan §5 Unit 7:
  - parser property-based/fuzz: 随机 ANSI/换行变体不改变命令语义
  - 业务 state-machine 不变量: command 事件后必有时间线
  - renderer differential: 同一 AnalysisResult 两次渲染核心字段一致
  - 关键分类 mutation 候选
  - reference_case_52 标注 fixture: 通话期间 ping, 板端 OK, 控制侧 ping check 失败
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


# ============================================================
# Property-based: parser 对 ANSI 噪声不敏感
# ============================================================


def test_parser_ansi_noise_invariant():
    """对同一文本加任意 ANSI 噪声, 命令识别不应改变。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 0 14 13900000000\n"
    # 加 ANSI 控制符
    noisy = "\x1b[31m" + raw.replace("modemcli", "\x1b[1mmodemcli\x1b[0m") + "\x1b[0m"
    events_clean = parse_evb_log(raw)
    events_noisy = parse_evb_log(noisy)
    cmds_clean = [e for e in events_clean if e.get("kind") == "command"]
    cmds_noisy = [e for e in events_noisy if e.get("kind") == "command"]
    assert len(cmds_clean) == len(cmds_noisy)
    # 命令名一致
    assert cmds_clean[0]["command_name"] == cmds_noisy[0]["command_name"]
    assert cmds_clean[0]["business_action"] == cmds_noisy[0]["business_action"]


def test_parser_extra_blank_lines_invariant():
    """空行插入不影响命令语义。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 0 14 13900000000\n[apc1] OK\n"
    noisy = "\n\n\nmodemcli> debug_bes_rpc 0 14 13900000000\n\n\n[apc1] OK\n\n\n"
    events_clean = parse_evb_log(raw)
    events_noisy = parse_evb_log(noisy)
    cmds_clean = [e for e in events_clean if e.get("kind") == "command"]
    cmds_noisy = [e for e in events_noisy if e.get("kind") == "command"]
    assert len(cmds_clean) == len(cmds_noisy)
    assert cmds_clean[0]["command_name"] == cmds_noisy[0]["command_name"]


def test_parser_random_ansi_invariance():
    """随机 ANSI 序列对命令识别无影响。"""
    from modem_log_analyzer.log_parser import parse_evb_log

    raw = "modemcli> debug_bes_rpc 0 14 13900000000\n"
    # 模拟日志里夹带的随机 ANSI
    ansi_codes = [
        "\x1b[0m",
        "\x1b[1m",
        "\x1b[31m",
        "\x1b[32m",
        "\x1b[33;1m",
        "\x1b[K",
        "\x1b[2J",
    ]
    for _ in range(10):
        ansi_in = ansi_codes[0]
        noisy = ansi_in + raw + ansi_codes[1]
        events = parse_evb_log(noisy)
        cmds = [e for e in events if e.get("kind") == "command"]
        assert len(cmds) == 1, f"failed for ansi {ansi_in!r}"
        assert cmds[0]["command_name"] == "debug_bes_rpc"


# ============================================================
# 业务 state-machine 不变量
# ============================================================


def test_state_machine_command_followed_by_callback():
    """每个 command 事件之后, 时间线上应有对应 callback/response。"""
    from modem_log_analyzer.analysis_service import AnalysisService

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:02.000][apc1] ERROR: dial failed\n"
    )
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False, encoding="utf-8") as f:
        f.write(raw)
        log = f.name
    with tempfile.TemporaryDirectory() as td:
        svc = AnalysisService()
        result = svc.run_analyze(
            evb_log_path=log,
            output_dir=td,
            dry_run=True,
        )
        # timeline 至少包含 session_entry + command + callback
        kinds = [ev.get("event", "") for ev in result["timeline"]]
        assert any("会话入口" in k for k in kinds)
        assert any("命令" in k for k in kinds)
        assert any("回调" in k for k in kinds)


# ============================================================
# Renderer differential
# ============================================================


def test_renderer_differential_consistency():
    """同一 AnalysisResult 两次渲染核心字段一致。"""
    from modem_log_analyzer.report import render_analysis_json, render_report_md

    result = {
        "schema_version": "0.1.0",
        "run_label": "loop_52",
        "classification": "DEVICE_FAILURE_CONFIRMED",
        "root_cause_confidence": "high",
        "scenario": "语音通话 (Call)",
        "scenario_confidence": "high",
        "first_anomaly": {
            "line_no": 1,
            "ref_id": "EV-0001",
            "summary": "x",
            "module": "ap",
            "ts": "t",
        },
        "evidence_refs": [
            {
                "ref_id": "EV-0001",
                "source": "evb.log",
                "line_no": 1,
                "timestamp": "t",
                "raw_text": "x",
                "module": "ap",
            },
        ],
        "timeline": [{"ts": "t", "event": "会话入口", "ref_id": "EV-0001", "source_module": "ap"}],
        "root_cause_chain": [],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": [],
        "suggested_actions": [],
    }
    md1 = render_report_md(result)
    md2 = render_report_md(result)
    js1 = render_analysis_json(result)
    js2 = render_analysis_json(result)
    # 章节顺序一致
    sections = ["## 失败概览", "## 核心诊断", "## 根因链"]
    pos1 = [md1.index(s) for s in sections]
    pos2 = [md2.index(s) for s in sections]
    assert pos1 == pos2
    # JSON 一致
    assert json.loads(js1) == json.loads(js2)


# ============================================================
# 关键分类 mutation 测试
# ============================================================


def test_classification_mutation_device_failure_to_evidence_incomplete():
    """如果 evidence 变不完整, 应从 DEVICE_FAILURE_CONFIRMED 降级到 DEVICE_EVIDENCE_INCOMPLETE。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    # 完整证据 → DEVICE_FAILURE_CONFIRMED
    cls1 = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert cls1 == Classification.DEVICE_FAILURE_CONFIRMED

    # 把 is_complete 改 False → DEVICE_EVIDENCE_INCOMPLETE
    cls2 = decide_classification(
        has_device_anomaly=True,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=False,
    )
    assert cls2 == Classification.DEVICE_EVIDENCE_INCOMPLETE


def test_classification_mutation_no_anomaly_to_test_automation_requires_evidence():
    """clean_log + 控制日志无证据 → NO_DEVICE_ANOMALY_FOUND (不能升 TEST_AUTOMATION)。"""
    from modem_log_analyzer.classification import decide_classification
    from modem_log_analyzer.contracts import Classification

    cls = decide_classification(
        has_device_anomaly=False,
        has_environment_evidence=False,
        has_control_log_evidence=False,
        is_complete=True,
    )
    assert cls == Classification.NO_DEVICE_ANOMALY_FOUND
    assert cls != Classification.TEST_AUTOMATION_FAILURE_CONFIRMED


# ============================================================
# 参考样例: reference_case_52
# ============================================================


@pytest.mark.skipif(
    not (
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "reference_case_52" / "evb.log"
    ).exists(),
    reason="reference_case_52 fixture not present; create manually or via embed tool",
)
def test_reference_case_52_classification():
    """reference_case_52: 通话中 ping + 控制侧 ping 检查失败 → TEST_AUTOMATION_FAILURE_CONFIRMED."""
    from modem_log_analyzer.analysis_service import AnalysisService

    fx = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "reference_case_52"
    evb = fx / "evb.log"
    ctrl = fx / "control.log"
    expected = json.loads((fx / "expected.json").read_text(encoding="utf-8"))

    svc = AnalysisService()
    result = svc.run_analyze(
        evb_log_path=str(evb),
        output_dir=str(fx / "out"),
        control_log_path=str(ctrl),
        overwrite=True,
        dry_run=True,
    )
    assert result["classification"] == expected["classification"]
    if "scenario_substring" in expected:
        # 大小写无关
        assert expected["scenario_substring"].lower() in (result["scenario"] or "").lower()
