"""ModemLogAnalyzer —— 控制脚本日志按需请求策略 (Unit 5)。

按 Plan §1 R15-R16 + §5 Unit 5:
  - 当 EVB 证据不足 + 外部 FAIL → 通过 interrupt 请求同次执行的控制脚本日志。
  - 用户可提供路径恢复, 或拒绝 (control_log_path=None) 触发诚实降级。
  - 只有控制日志含**直接证据**(断言错误 / 超时 / 显式 FAIL) 才能把分类升级为
    ``TEST_AUTOMATION_FAILURE_CONFIRMED``。
"""

from __future__ import annotations

import re
from typing import Any

# ============================================================
# 控制日志解析 (轻量级, 仅识别断言/超时/FAIL)
# ============================================================
_AUTOMATION_EVIDENCE_PATTERNS = [
    re.compile(r"\bAssertionError\b", re.IGNORECASE),
    re.compile(r"\bTimeoutError\b", re.IGNORECASE),
    re.compile(r"\bassertion\s+failed\b", re.IGNORECASE),
    re.compile(r"\bexpected\b.*\bgot\b", re.IGNORECASE),
    re.compile(r"\bcase_result\s*[:=]\s*FAIL\b", re.IGNORECASE),
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r"\bEXCEPTION\b"),
    # 真实控制脚本 (auto_case_modem_52): ``ERROR ... check ping ... fail``
    re.compile(r"\bERROR\b.*\bcheck ping\b.*\bfail\b", re.IGNORECASE),
    re.compile(r"\bERROR\b.*\bfail\b", re.IGNORECASE),
    re.compile(r"\bcheck ping\b.*\bfail\b", re.IGNORECASE),
]


def parse_control_log(raw: str) -> list[dict[str, Any]]:
    """解析控制脚本日志 → 简化事件列表。

    与 EVB parser 不同: 控制日志不需要逐字段提取, 只需要识别"是否有直接证据"。
    """
    events: list[dict[str, Any]] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        has_evidence = any(p.search(line) for p in _AUTOMATION_EVIDENCE_PATTERNS)
        events.append(
            {
                "line_no": i,
                "raw_text": line,
                "has_direct_evidence": has_evidence,
            }
        )
    return events


# ============================================================
# 是否应请求控制日志
# ============================================================
def should_request_control_log(
    *,
    first_anomaly: dict | None,
    classification: str,
    has_control_log: bool,
) -> bool:
    """决策: 是否应请求用户提供同次执行的控制脚本日志?

    规则:
      - 已提供 → False (不重复请求)
      - 板端已确认 → False (无需控制日志归因)
      - 板端无异常 + 外部 FAIL → True (板端无法解释, 需要板外信息)
      - 证据不完整 → 也请求 (作为补充)
    """
    if has_control_log:
        return False
    if classification == "DEVICE_FAILURE_CONFIRMED":
        return False
    if first_anomaly is not None:
        return False
    return True


# ============================================================
# 控制日志是否提供直接证据
# ============================================================
def has_direct_automation_evidence(events: list[dict[str, Any]]) -> bool:
    """扫描 events 看是否存在直接证据。

    直接证据: AssertionError / TimeoutError / assertion failed / case_result=FAIL 等。
    """
    for ev in events:
        if ev.get("has_direct_evidence"):
            return True
    return False


# ============================================================
# 用户选择后的最终分类
# ============================================================
def finalize_classification_after_user_choice(
    *,
    initial_classification: str,
    user_provided_control_log: bool,
    control_log_has_direct_evidence: bool,
) -> str:
    """根据用户是否提供控制日志 + 证据, 决定最终分类。

    规则 (Plan R16):
      - 没提供 / 无直接证据 → 保持 initial_classification
      - 提供 + 有直接证据 → 升级为 TEST_AUTOMATION_FAILURE_CONFIRMED
    """
    if not user_provided_control_log:
        return initial_classification
    if not control_log_has_direct_evidence:
        return initial_classification
    return "TEST_AUTOMATION_FAILURE_CONFIRMED"


# ============================================================
# Resume / Interrupt payload
# ============================================================
def build_resume_payload(control_log_path: str | None) -> dict[str, Any]:
    """构造 LangGraph Command(resume=...) 的 payload。"""
    return {"control_log_path": control_log_path}


def build_interrupt_request(reason: str) -> dict[str, Any]:
    """构造 interrupt 请求负载 (供 LangGraph interrupt() 调用)。

    包含 why 字段, 解释为何需要控制脚本日志, 便于 CLI 提示用户。
    """
    return {
        "type": "REQUEST_CONTROL_LOG",
        "why": reason,
        "options": {
            "approve": "提供控制脚本日志路径",
            "reject": "不提供 (诚实降级)",
        },
    }


__all__ = [
    "parse_control_log",
    "should_request_control_log",
    "has_direct_automation_evidence",
    "finalize_classification_after_user_choice",
    "build_resume_payload",
    "build_interrupt_request",
]
