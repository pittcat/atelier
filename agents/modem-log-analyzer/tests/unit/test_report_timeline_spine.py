"""U1 ATDD: Timeline Spine 报告外部可观察行为 (Red)。

按 Plan `docs/plans/2026-07-21-002-feat-modem-report-timeline-spine-plan.md`:
  - Scenario S1-S4, S6-S7, S9
  - AE1-AE3 的渲染结构断言
  - 本 Unit 仅写验收测试; 不实现生产代码, 允许因字段缺失/渲染未实现而 Red。
  - 禁止 skip/xfail; 失败原因须清晰指向「缺失领口/时间线/分块」而非 import 崩坏。

Driver: `uv run pytest tests/unit/test_report_timeline_spine.py`
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

FIXTURE = ROOT / "tests" / "fixtures" / "reports" / "timeline_spine_case52_draft.json"


def _load_draft() -> dict:
    """加载 case52 风格合成草稿。"""
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def _render() -> str:
    from modem_log_analyzer.report import render_report_md

    return render_report_md(_load_draft())


# ============================================================
# Fixture 完整性: 目标草稿含 spine 字段 (S1/S3/S4 数据基础)
# ============================================================


def test_fixture_contains_spine_fields():
    """Fixture 必须含 Timeline Spine 目标字段 (否则后续断言无意义)。"""
    d = _load_draft()
    assert d["root_cause_confidence"] == "low"
    assert d.get("flow_one_liner"), "fixture 缺 flow_one_liner"
    assert d.get("confirmed_impact"), "fixture 缺 confirmed_impact"
    assert d.get("suspected_root_cause"), "fixture 缺 suspected_root_cause"
    assert any(ev.get("is_failure_step") for ev in d["timeline"]), "timeline 无 is_failure_step"
    assert d.get("evidence_blocks"), "fixture 缺 evidence_blocks"


# ============================================================
# S9: 既有章节标题契约不回归
# ============================================================


def test_report_keeps_ten_sections_in_order():
    """R19 / S9: 十个中文章节标题顺序不变。"""
    md = _render()
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
    assert positions == sorted(positions), "章节顺序被破坏"


# ============================================================
# S1: 低置信领口 = 「已确认 → 疑似」 + 一行流程
# ============================================================


def test_low_confidence_lead_starts_with_confirmed_impact():
    """R2 / S1: 低置信领口先陈述已确认现象/影响。"""
    md = _render()
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    ci_pos = overview.find("外部测试 FAIL")
    assert ci_pos != -1, "领口未出现 confirmed_impact 内容"
    # 「疑似」必须在 confirmed_impact 之后
    suspected_pos = overview.find("疑似")
    assert suspected_pos != -1, "领口未出现「疑似」措辞"
    assert suspected_pos > ci_pos, "低置信时「疑似」应在已确认现象之后"


def test_low_confidence_lead_contains_flow_one_liner():
    """R4 / S1: 领口须含一行短流程摘要。"""
    md = _render()
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    assert "Data 检查" in overview, "领口缺 flow_one_liner"
    assert "!ping" in overview


def test_low_confidence_lead_not_using_confirmed_tone_for_suspected():
    """R2 / S1: 不得用已确认语气包装低置信根因。"""
    md = _render()
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    # 领口出现「根因是」「已确认根因」等强主张应失败
    for forbidden in ["已确认根因", "根因是", "根因已确定"]:
        assert forbidden not in overview, f"领口用已确认语气: {forbidden}"


# ============================================================
# S2: 高/中置信领口 = 「根因 → 影响」 (反例测试)
# ============================================================


def test_high_confidence_lead_orders_root_cause_before_impact():
    """R3 / S2: 中/高置信时领口先陈述根因主张, 再陈述影响。"""
    from modem_log_analyzer.report import render_report_md

    d = _load_draft()
    d["root_cause_confidence"] = "high"
    md = render_report_md(d)
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    # 高置信: suspected_root_cause 内容应在 confirmed_impact 之前
    suspected_pos = overview.find("ping 首包")
    impact_pos = overview.find("外部测试 FAIL")
    assert suspected_pos != -1, "高置信领口缺根因主张"
    assert impact_pos != -1, "高置信领口缺影响"
    assert suspected_pos < impact_pos, "高置信应根因→影响"


# ============================================================
# S3: 失败时间线非空且标记故障步
# ============================================================


def test_timeline_not_empty_when_device_anomaly_claimed():
    """R5 / S3 / S8: 声称板端偏离时时间线不得为空。"""
    md = _render()
    timeline_section = md.split("## 失败时间线", 1)[1].split("##", 1)[0]
    assert "无关键业务事件" not in timeline_section, "时间线被渲染为空"
    assert "No response" in timeline_section or "故障步" in timeline_section


def test_timeline_marks_failure_step():
    """R6 / S3: 时间线必须明确标记故障步。"""
    md = _render()
    timeline_section = md.split("## 失败时间线", 1)[1].split("##", 1)[0]
    # 故障步标记: 接受 ✗ / [故障步] / (故障步) / ⚠ / FAIL 等显式标记
    markers = ["故障步", "✗", "⚠", "[FAIL]", " failure", " Failure"]
    assert any(m in timeline_section for m in markers), (
        f"时间线未显式标记故障步; 期望出现 {markers} 之一"
    )


def test_timeline_order_matches_execution():
    """R5 / S3: 时间线顺序与测试执行一致 (ping → sms)。"""
    md = _render()
    timeline_section = md.split("## 失败时间线", 1)[1].split("##", 1)[0]
    ping_pos = timeline_section.find("!ping")
    sms_pos = timeline_section.find("debug_bes_rpc 4")
    assert ping_pos != -1 and sms_pos != -1, "时间线缺 ping 或 sms 步骤"
    assert ping_pos < sms_pos, "时间线顺序与执行不一致"


# ============================================================
# S4: 设备 log 按步骤分块, 故障步含前后对照
# ============================================================


def test_evidence_section_blocks_by_step():
    """R9 / S4: 「测试步骤与日志证据」按测试步骤分块。"""
    md = _render()
    section = md.split("## 测试步骤与日志证据", 1)[1].split("##", 1)[0]
    # 步骤标签: ping / sms
    assert "ping" in section.lower(), "证据节缺 ping 步骤块"
    assert "sms" in section.lower(), "证据节缺 sms 步骤块"
    # 设备原文: 板端 modemcli 命令与 No response 必须出现
    assert "No response" in section, "证据块缺板端 No response 原文"
    assert "debug_bes_rpc 4" in section, "证据块缺 SMS 命令原文"


def test_failure_step_block_has_before_after_context():
    """R10 / S4: 故障步块须含前后对照 (before/after)。"""
    md = _render()
    section = md.split("## 测试步骤与日志证据", 1)[1].split("##", 1)[0]
    # 故障主块: No response icmp_seq=0
    assert "icmp_seq=0" in section, "故障主块缺 EV-0002 原文"
    # 前对照: ping 命令本身 (EV-0001)
    assert "!ping -c 60" in section, "故障步缺 before (启动命令)"
    # 后对照: icmp_seq=1 恢复 (EV-0003)
    assert "icmp_seq=1" in section, "故障步缺 after (恢复)"


def test_control_script_raw_text_not_in_evidence_blocks():
    """R12 / S4: 控制脚本日志原文不得进入证据分块。"""
    md = _render()
    section = md.split("## 测试步骤与日志证据", 1)[1].split("##", 1)[0]
    # control_script.log 标志性内容: env_inf.py / case_execute_action.py / ims_device_state_check_inf.py
    forbidden_markers = [
        "env_inf.py",
        "case_execute_action.py",
        "ims_device_state_check_inf.py",
        "system_log_interface.py",
        "tcp_client_action.py",
        "control_script.log",
    ]
    for m in forbidden_markers:
        assert m not in section, f"证据块出现控制脚本原文特征: {m}"


# ============================================================
# S6: 长场景不得三重重复
# ============================================================


def test_scenario_section_short_no_triple_repeat():
    """R7 / R8 / S6: 「推断的测试场景与基线」压短; 同一长段不三重粘贴。"""
    md = _render()
    scenario_section = md.split("## 推断的测试场景与基线", 1)[1].split("##", 1)[0]
    # scenario 原文不应整段在概览、场景、诊断三处重复
    # 这里测: scenario 段落不应超过 ~400 字 (压短)
    assert len(scenario_section) < 600, (
        f"场景节过长 ({len(scenario_section)} chars), 应压短为流程/动作摘要"
    )
    # scenario 不应整段出现在「失败概览」(避免领口与场景重复)
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    draft = _load_draft()
    scenario_full = draft.get("scenario", "")
    # 完整 scenario 字串不应在概览出现 (避免长文复制)
    if len(scenario_full) > 60:
        assert scenario_full not in overview, "scenario 长文被复制到概览"


# ============================================================
# S7: 建议行动可空
# ============================================================


def test_empty_suggested_actions_renders_without_failure():
    """R15 / S7: 空 suggested_actions 仍能渲染且不判定失败。"""
    md = _render()
    actions_section = md.split("## 建议行动", 1)[1].split("##", 1)[0]
    # 允许「无额外建议」之类占位
    assert "## 建议行动" in md
    # 不应因为空 actions 出现异常字符
    assert "Traceback" not in actions_section
    assert "None" not in actions_section or "无额外建议" in actions_section


# ============================================================
# AE1 / AE2: 整体领口-时间线-证据一致性
# ============================================================


def test_lead_claims_have_corroborating_device_evidence():
    """R11 / AE2: 领口关键断言必须有可复核的设备侧证据引用。"""
    md = _render()
    section = md.split("## 测试步骤与日志证据", 1)[1].split("##", 1)[0]
    # 领口声称「首包超时」→ 证据块须含 No response 原文
    assert "No response" in section, "领口断言「首包超时」缺设备原文支撑"
    # 禁止空壳 modemcli> 作为断言唯一支撑 (No response 行须有实质内容)
    lines = section.splitlines()
    for ln in lines:
        stripped = ln.strip().lstrip("-").strip()
        # 出现 modemcli> 但其后无实质内容 → 空壳
        if "modemcli>" in stripped and "No response" not in stripped:
            # 允许命令本身 (如 !ping), 但纯提示符 + 空白禁止
            after = stripped.split("modemcli>", 1)[1].strip()
            # 移除 ANSI / [K 控制字符
            import re

            after_clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\[K", "", after).strip()
            assert after_clean != "", f"空壳 modemcli> 提示符冒充证据: {ln!r}"


def test_overview_external_result_and_device_step_both_present():
    """R1 / AE1: 领口能复述外部 FAIL + 板端偏离步。"""
    md = _render()
    overview = md.split("## 失败概览", 1)[1].split("##", 1)[0]
    assert "FAIL" in overview, "领口缺外部结果"
    # 板端偏离步: ping / 首包超时
    assert "ping" in overview.lower() or "首包" in overview, "领口缺板端偏离步"
