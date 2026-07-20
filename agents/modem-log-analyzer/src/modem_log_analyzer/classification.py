"""ModemLogAnalyzer —— 顶层分类决策 (Unit 4)。

按 Plan §1 R13/R14 + §5 Unit 4:
  - 顶层分类必须使用 6 个枚举之一, 严格互斥。
  - ``TEST_AUTOMATION_FAILURE_CONFIRMED`` 必须有控制脚本日志直接证据。
  - 证据不完整时, 优先使用 ``DEVICE_EVIDENCE_INCOMPLETE`` 而不是过早判断。
  - 多条候选根因时使用 ``MULTIPLE_POSSIBLE_CAUSES``。
  - 仅 EVB 日志 + 板端正常 → ``NO_DEVICE_ANOMALY_FOUND``, **不等于**自动化误报。
"""

from __future__ import annotations

from collections.abc import Iterable

from modem_log_analyzer.contracts import Classification
from modem_log_analyzer.evidence import EvidenceRef


# ============================================================
# 分类决策
# ============================================================
def decide_classification(
    *,
    has_device_anomaly: bool,
    has_environment_evidence: bool,
    has_control_log_evidence: bool,
    is_complete: bool,
) -> Classification:
    """根据四类输入决策顶层分类。

    决策矩阵 (优先级从高到低):
      1. 有控制日志直接证据 (无板端异常) → TEST_AUTOMATION_FAILURE_CONFIRMED
      2. 设备异常 + 完整证据 + 无环境证据 → DEVICE_FAILURE_CONFIRMED
      3. 环境指征明确 → ENVIRONMENT_FAILURE_INDICATED
      4. 设备异常 + 不完整 → DEVICE_EVIDENCE_INCOMPLETE
      5. 设备异常 + 环境异常并存 → MULTIPLE_POSSIBLE_CAUSES
      6. 无任何异常 + 完整 → NO_DEVICE_ANOMALY_FOUND
      7. 无任何异常 + 不完整 → DEVICE_EVIDENCE_INCOMPLETE
    """
    if has_control_log_evidence and not has_device_anomaly and not has_environment_evidence:
        return Classification.TEST_AUTOMATION_FAILURE_CONFIRMED

    if has_device_anomaly and is_complete and not has_environment_evidence:
        return Classification.DEVICE_FAILURE_CONFIRMED

    if has_environment_evidence and not has_device_anomaly:
        return Classification.ENVIRONMENT_FAILURE_INDICATED

    if has_device_anomaly and not is_complete:
        return Classification.DEVICE_EVIDENCE_INCOMPLETE

    if has_device_anomaly and has_environment_evidence:
        return Classification.MULTIPLE_POSSIBLE_CAUSES

    if not has_device_anomaly and is_complete:
        return Classification.NO_DEVICE_ANOMALY_FOUND

    # 兜底: 不完整 + 无明显异常
    return Classification.DEVICE_EVIDENCE_INCOMPLETE


# ============================================================
# 置信度
# ============================================================
def compute_root_cause_confidence(
    *,
    n_supporting_refs: int,
    n_gaps: int,
    classification: Classification,
) -> str:
    """计算根因置信度。

    规则 (简化版):
      - classification == NO_DEVICE_ANOMALY_FOUND → "high" (板端 OK 是硬事实)
      - n_gaps >= 3 或 n_supporting_refs == 0 → "low"
      - n_supporting_refs >= 3 且 n_gaps <= 1 → "high"
      - 中间档 → "medium"
    """
    if classification == Classification.NO_DEVICE_ANOMALY_FOUND:
        return "high"

    if n_gaps >= 3 or n_supporting_refs == 0:
        return "low"
    if n_supporting_refs >= 3 and n_gaps <= 1:
        return "high"
    return "medium"


# ============================================================
# 首异常识别 (R12)
# ============================================================
_ANOMALY_KEYWORDS = ("ERROR", "FAIL", "EXCEPTION", "TIMEOUT", "REJECT")


def _is_anomaly_event(ev: dict) -> bool:
    """根据文本判定事件是否构成异常。

    Plan §1 R12: 只有具备命令、状态或时序支持的事件才能进入因果链。
    """
    text = (ev.get("raw_text") or "").upper()
    return any(k in text for k in _ANOMALY_KEYWORDS)


def find_first_anomaly(
    events: list[dict],
    refs: Iterable[EvidenceRef],
) -> dict | None:
    """找到最早的板端异常, 返回 {line_no, ref_id, summary}。

    若无任何异常 → 返回 None。
    """
    refs_list = list(refs)
    by_line: dict[int, EvidenceRef] = {r.line_no: r for r in refs_list if r.line_no}
    for ev in events:
        ln = int(ev.get("line_no") or 0)
        if not _is_anomaly_event(ev):
            continue
        # 必须有对应 evidence ref
        ref = by_line.get(ln)
        if ref is None:
            continue
        # 仅当 terminal_outcome == "failure" 或 evidence raw_text 含关键字时纳入
        if (ev.get("terminal_outcome") == "failure") or _is_anomaly_event(ev):
            return {
                "line_no": ln,
                "ref_id": ref.ref_id,
                "summary": (ev.get("raw_text") or "").strip()[:200],
                "kind": ev.get("kind"),
                "module": ev.get("module"),
                "ts": ev.get("device_ts") or ev.get("capture_ts"),
            }
    return None


__all__ = [
    "decide_classification",
    "compute_root_cause_confidence",
    "find_first_anomaly",
]
