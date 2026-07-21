"""U4: spine_validate 校验门禁测试 (S5/S8)。

按 Plan `docs/plans/2026-07-21-002-feat-modem-report-timeline-spine-plan.md`:
  - 规则1: 声称板端偏离 (有 first_anomaly 或 confirmed_impact) 时, timeline 非空
           且存在 is_failure_step。
  - 规则2: 领口字段按 confidence 齐备 (low 需 confirmed_impact + suspected_root_cause;
           medium/high 需 suspected_root_cause)。
  - 规则3: 断言引用的 ref 非空壳, 且在 evidence_refs 内。
  - 规则4: evidence_blocks 不得引用控制脚本源。
  - 兼容模式: 旧最小草稿 (无 first_anomaly 且空 timeline) 仍允许。

Driver: `uv run pytest tests/unit/test_spine_validate.py`
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE = ROOT / "tests" / "fixtures" / "reports" / "timeline_spine_case52_draft.json"


def _load_draft() -> dict[str, Any]:
    import json

    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def _import_validator():
    from modem_log_analyzer import spine_validate

    return spine_validate


# ============================================================
# 规则1: 声称板端偏离 → timeline 非空 + is_failure_step
# ============================================================


def test_valid_case52_draft_passes():
    """Fixture 草稿须通过 spine 校验。"""
    sv = _import_validator()
    result = sv.validate_spine(_load_draft())
    assert result.is_valid, f"expected VALID, got: {result.reason}"


def test_empty_timeline_with_first_anomaly_rejected():
    """S8: 声称板端偏离 (first_anomaly) 但 timeline 空 → INVALID。"""
    sv = _import_validator()
    d = _load_draft()
    d["timeline"] = []
    d["evidence_blocks"] = []
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "timeline" in result.reason.lower() or "时间线" in result.reason


def test_timeline_without_failure_step_rejected():
    """R6: 声称板端偏离但 timeline 无 is_failure_step → INVALID。"""
    sv = _import_validator()
    d = _load_draft()
    for ev in d["timeline"]:
        ev["is_failure_step"] = False
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "failure_step" in result.reason.lower() or "故障步" in result.reason


def test_legacy_minimal_draft_without_anomaly_allowed():
    """兼容模式: 旧最小草稿 (无 first_anomaly 且空 timeline) 仍允许。"""
    sv = _import_validator()
    minimal: dict[str, Any] = {
        "schema_version": "0.1.0",
        "classification": "NO_DEVICE_ANOMALY_FOUND",
        "root_cause_confidence": "low",
        "first_anomaly": None,
        "confirmed_impact": None,
        "timeline": [],
        "evidence_refs": [],
        "evidence_blocks": [],
    }
    result = sv.validate_spine(minimal)
    assert result.is_valid, f"legacy minimal should be VALID, got: {result.reason}"


# ============================================================
# 规则2: 领口字段按 confidence 齐备
# ============================================================


def test_low_confidence_requires_confirmed_impact():
    """R2: low 置信需 confirmed_impact。"""
    sv = _import_validator()
    d = _load_draft()
    d["confirmed_impact"] = None
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "confirmed_impact" in result.reason or "已确认" in result.reason


def test_low_confidence_requires_suspected_root_cause():
    """R2: low 置信需 suspected_root_cause。"""
    sv = _import_validator()
    d = _load_draft()
    d["suspected_root_cause"] = None
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "suspected_root_cause" in result.reason or "疑似根因" in result.reason


def test_high_confidence_requires_suspected_root_cause():
    """R3: medium/high 置信需 suspected_root_cause (根因主张)。"""
    sv = _import_validator()
    d = _load_draft()
    d["root_cause_confidence"] = "high"
    d["suspected_root_cause"] = None
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "suspected_root_cause" in result.reason or "根因主张" in result.reason


def test_flow_one_liner_required_when_spine_active():
    """R4: spine 激活时需 flow_one_liner。"""
    sv = _import_validator()
    d = _load_draft()
    d["flow_one_liner"] = None
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "flow_one_liner" in result.reason or "流程" in result.reason


# ============================================================
# 规则3: 断言引用的 ref 非空壳, 且在 evidence_refs 内
# ============================================================


def test_evidence_block_ref_not_in_evidence_refs_rejected():
    """R11: evidence_blocks 引用的 ref_id 必须在 evidence_refs 内。"""
    sv = _import_validator()
    d = _load_draft()
    d["evidence_blocks"][0]["ref_ids"] = ["EV-9999"]  # 不存在
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "EV-9999" in result.reason or "ref_id" in result.reason.lower()


def test_empty_shell_evidence_rejected():
    """S5: 空壳 modemcli> 提示符不得作为断言唯一支撑。"""
    sv = _import_validator()
    d = _load_draft()
    # 把故障步主块 ref 替换为空壳证据
    d["evidence_refs"][1]["raw_text"] = "2026-05-27 [21:34:12.605222] modemcli> [K"
    result = sv.validate_spine(d)
    assert not result.is_valid
    reason = result.reason
    assert "空壳" in reason or "shell" in reason.lower() or "modemcli" in reason


def test_first_anomaly_ref_must_exist():
    """R11: first_anomaly.ref_id 必须在 evidence_refs 内。"""
    sv = _import_validator()
    d = _load_draft()
    d["first_anomaly"]["ref_id"] = "EV-9999"
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "EV-9999" in result.reason or "first_anomaly" in result.reason.lower()


# ============================================================
# 规则4: evidence_blocks 不得引用控制脚本源
# ============================================================


def test_control_script_ref_in_evidence_blocks_rejected():
    """R12: evidence_blocks 引用控制脚本源 → INVALID。"""
    sv = _import_validator()
    d = _load_draft()
    # 在 evidence_refs 加一个控制脚本源 ref, 并让 evidence_blocks 引用它
    d["evidence_refs"].append(
        {
            "ref_id": "EV-CTRL",
            "source": "control_script.log",
            "line_no": 1,
            "timestamp": None,
            "raw_text": "device:1 send cmd:!ping",
            "module": "control",
        }
    )
    d["evidence_blocks"].append(
        {
            "step_label": "ping",
            "is_failure_step": False,
            "role": "main",
            "ref_ids": ["EV-CTRL"],
        }
    )
    result = sv.validate_spine(d)
    assert not result.is_valid
    assert "control" in result.reason.lower() or "控制脚本" in result.reason


# ============================================================
# validate_analysis_draft_tool 集成 (tools.py)
# ============================================================


def test_validate_analysis_draft_tool_rejects_bad_spine():
    """tools.validate_analysis_draft_tool 须调用 spine 规则。"""
    from modem_log_analyzer.tools import validate_analysis_draft_tool

    d = _load_draft()
    d["timeline"] = []
    d["evidence_blocks"] = []
    out = validate_analysis_draft_tool(d)
    assert out.startswith("INVALID")
    assert "timeline" in out.lower() or "时间线" in out


def test_validate_analysis_draft_tool_accepts_valid():
    from modem_log_analyzer.tools import validate_analysis_draft_tool

    out = validate_analysis_draft_tool(_load_draft())
    assert out.startswith("VALID"), f"expected VALID, got: {out}"


def test_validate_analysis_draft_tool_accepts_legacy_minimal():
    """旧最小草稿仍 VALID (兼容模式)。"""
    from modem_log_analyzer.tools import validate_analysis_draft_tool

    minimal: dict[str, Any] = {
        "schema_version": "0.1.0",
        "classification": "NO_DEVICE_ANOMALY_FOUND",
        "root_cause_confidence": "low",
        "first_anomaly": None,
        "timeline": [],
        "evidence_refs": [],
    }
    out = validate_analysis_draft_tool(minimal)
    assert out.startswith("VALID"), f"legacy minimal should be VALID, got: {out}"
