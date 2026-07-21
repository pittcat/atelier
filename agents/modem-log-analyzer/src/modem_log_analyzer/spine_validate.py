"""ModemLogAnalyzer —— Timeline Spine 校验门禁 (Plan 2026-07-21-002 / U4)。

在 Pydantic schema 校验之后, 对 AnalysisResult 草稿追加可测试的 spine 规则:

  1. 声称板端偏离 (有 ``first_anomaly`` 或非空 ``confirmed_impact``) 时,
     ``timeline`` 非空且存在 ``is_failure_step=True`` 的步骤。 (R5/R6/S3/S8)
  2. 领口字段按 ``root_cause_confidence`` 齐备:
     - low:  ``confirmed_impact`` + ``suspected_root_cause`` + ``flow_one_liner``
     - medium/high: ``suspected_root_cause`` + ``flow_one_liner``  (R2/R3/R4)
  3. 断言引用的 ref 非空壳, 且在 ``evidence_refs`` 内:
     - ``first_anomaly.ref_id`` / ``evidence_blocks[].ref_ids`` 必须命中 evidence_refs
     - 故障步主块的 ref 不得是空壳 ``modemcli>`` (剥除 ANSI/控制字符后无实质报文)
       (R11/S5)
  4. ``evidence_blocks`` 不得引用控制脚本源。 (R12)

兼容模式: 旧最小草稿 (无 ``first_anomaly`` 且空 ``timeline``) 仍允许通过,
避免对未升级的草稿一刀切。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from modem_log_analyzer.contracts import AnalysisResult


@dataclass(frozen=True)
class SpineValidationResult:
    """Spine 校验结果。"""

    is_valid: bool
    reason: str

    @classmethod
    def ok(cls) -> SpineValidationResult:
        return cls(is_valid=True, reason="")

    @classmethod
    def invalid(cls, reason: str) -> SpineValidationResult:
        return cls(is_valid=False, reason=reason)


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[K")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "").strip()


def _is_control_script_source(source: str | None) -> bool:
    if not source:
        return False
    s = source.lower()
    return s.startswith("control") or "control_script" in s or "control.log" in s


def _has_substance(raw_text: str) -> bool:
    """判断 raw_text 是否含实质报文 (非空壳 modemcli> 提示符)。"""
    t = _strip_ansi(raw_text)
    # 剥除前导 modemcli> 提示符后剩余内容
    t2 = re.sub(r"^.*?modemcli>\s*", "", t).strip()
    # 剥除时间戳前缀
    t2 = re.sub(r"^\d{4}-\d{2}-\d{2}.*?\]\s*", "", t2).strip()
    return bool(t2)


def _spine_active(candidate: dict[str, Any]) -> bool:
    """是否激活 spine 强校验: 有 first_anomaly 或 confirmed_impact。"""
    fa = candidate.get("first_anomaly")
    if fa and isinstance(fa, dict) and fa.get("ref_id"):
        return True
    ci = candidate.get("confirmed_impact")
    if ci and isinstance(ci, str) and ci.strip():
        return True
    return False


def validate_spine(candidate: dict[str, Any]) -> SpineValidationResult:
    """对已通过 Pydantic 校验的草稿运行 spine 规则。

    返回 ``SpineValidationResult``。本函数不做 schema 校验;
    调用方应先 ``AnalysisResult.model_validate`` 再调用本函数。
    若 schema 不合法, 行为未定义 (会按字段缺失处理为 INVALID)。
    """
    # 兼容模式: 旧最小草稿 (无 first_anomaly 且空 timeline) 直接放行。
    if not _spine_active(candidate):
        # 仍检查 evidence_blocks 控制脚本源 (即使 spine 未激活)
        ctrl_err = _check_blocks_no_control(candidate)
        if ctrl_err:
            return SpineValidationResult.invalid(ctrl_err)
        return SpineValidationResult.ok()

    # 规则1: timeline 非空且存在 is_failure_step
    timeline = candidate.get("timeline") or []
    if not timeline:
        return SpineValidationResult.invalid(
            "spine: 声称板端偏离但 timeline 为空 (R5/S8)"
        )
    if not any(bool(ev.get("is_failure_step")) for ev in timeline):
        return SpineValidationResult.invalid(
            "spine: timeline 无 is_failure_step 故障步标记 (R6/S3)"
        )

    # 规则2: 领口字段按 confidence 齐备
    confidence = (candidate.get("root_cause_confidence") or "low").lower()
    flow = candidate.get("flow_one_liner")
    if not (isinstance(flow, str) and flow.strip()):
        return SpineValidationResult.invalid(
            "spine: 缺 flow_one_liner 流程摘要 (R4/S1)"
        )

    suspected = candidate.get("suspected_root_cause")
    if not (isinstance(suspected, str) and suspected.strip()):
        if confidence == "low":
            return SpineValidationResult.invalid(
                "spine: 低置信缺 suspected_root_cause (疑似根因) (R2/S1)"
            )
        return SpineValidationResult.invalid(
            "spine: 中/高置信缺 suspected_root_cause (根因主张) (R3/S2)"
        )

    if confidence == "low":
        confirmed = candidate.get("confirmed_impact")
        if not (isinstance(confirmed, str) and confirmed.strip()):
            return SpineValidationResult.invalid(
                "spine: 低置信缺 confirmed_impact (已确认现象/影响) (R2/S1)"
            )

    # 规则3: 断言引用的 ref 在 evidence_refs 内 + 非空壳
    evidence_refs = candidate.get("evidence_refs") or []
    valid_ref_ids = {
        r.get("ref_id") for r in evidence_refs if isinstance(r, dict) and r.get("ref_id")
    }
    refs_by_id = {
        r.get("ref_id"): r for r in evidence_refs if isinstance(r, dict) and r.get("ref_id")
    }

    fa = candidate.get("first_anomaly") or {}
    fa_ref = fa.get("ref_id")
    if fa_ref and fa_ref not in valid_ref_ids:
        return SpineValidationResult.invalid(
            f"spine: first_anomaly.ref_id {fa_ref!r} 不在 evidence_refs 内 (R11)"
        )

    blocks = candidate.get("evidence_blocks") or []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for rid in b.get("ref_ids") or []:
            if rid not in valid_ref_ids:
                return SpineValidationResult.invalid(
                    f"spine: evidence_blocks 引用了不存在的 ref_id {rid!r} (R11)"
                )
            ref = refs_by_id.get(rid) or {}
            raw = ref.get("raw_text") or ""
            # 故障步主块须非空壳
            if b.get("is_failure_step") and b.get("role", "main") == "main":
                if not _has_substance(raw):
                    return SpineValidationResult.invalid(
                        f"spine: 故障步主块 ref {rid!r} 为空壳 modemcli> 提示符, "
                        "无实质报文 (R11/S5)"
                    )

    # 规则4: evidence_blocks 不得引用控制脚本源
    ctrl_err = _check_blocks_no_control(candidate)
    if ctrl_err:
        return SpineValidationResult.invalid(ctrl_err)

    return SpineValidationResult.ok()


def _check_blocks_no_control(candidate: dict[str, Any]) -> str | None:
    """检查 evidence_blocks 引用的 ref 是否来自控制脚本; 返回错误信息或 None。"""
    evidence_refs = candidate.get("evidence_refs") or []
    refs_by_id = {
        r.get("ref_id"): r for r in evidence_refs if isinstance(r, dict) and r.get("ref_id")
    }
    blocks = candidate.get("evidence_blocks") or []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for rid in b.get("ref_ids") or []:
            ref = refs_by_id.get(rid)
            if ref and _is_control_script_source(ref.get("source")):
                return (
                    f"spine: evidence_blocks 引用了控制脚本源 ref {rid!r} "
                    f"(source={ref.get('source')!r}); 控制脚本原文不得进入分块 (R12)"
                )
    return None


def validate_analysis_draft(candidate: dict[str, Any]) -> SpineValidationResult:
    """组合校验: Pydantic schema + spine 规则。

    用于 ``validate_analysis_draft_tool`` 与 ``agent_runner`` 落盘前门禁。
    """
    try:
        AnalysisResult.model_validate(candidate)
    except Exception as e:  # noqa: BLE001 - 保留 Pydantic 错误信息
        return SpineValidationResult.invalid(f"schema: {e!s}")
    return validate_spine(candidate)


__all__ = [
    "SpineValidationResult",
    "validate_spine",
    "validate_analysis_draft",
]
