"""ModemLogAnalyzer —— 公共契约 (Public Contracts)。

锁定:
  - ``Classification`` 枚举: 6 个顶层诊断分类 (需求 R13)
  - ``ANALYSIS_SCHEMA_VERSION``: analysis.json 的 schema 版本字符串
  - ``RunRequest``: CLI 入口接受的最小请求
  - ``AnalysisResult``: 诊断产物的最终结构化结果（Plan 锁定）
  - ``EvidenceRef``: 原始日志证据的稳定引用
  - ``TimelineEvent`` / ``CausalChainLink``: 时间线与根因链节点

按 plan §1 + §3:
  - 模型对模型的 schema 契约保持最小可验证的公共字段。
  - 单位元数据(可选字段)允许扩展,但不破坏主键。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrEnum(str, Enum):  # noqa: UP042 - Python 3.11 has no StrEnum
    """str + Enum 子类, Python 3.11 没有内置 StrEnum。

    在 3.11+ 上可用, 与 ``enum.StrEnum``(3.11+) 等价。
    """

    pass


ANALYSIS_SCHEMA_VERSION = "0.1.0"


# ============================================================
# 诊断分类（顶层枚举，需求 R13）
# ============================================================
class Classification(_StrEnum):
    """顶层诊断分类（Plan §1, R13）。

    - DEVICE_FAILURE_CONFIRMED:        板端证据明确确认产品故障
    - ENVIRONMENT_FAILURE_INDICATED:   环境/网络异常指征明确
    - TEST_AUTOMATION_FAILURE_CONFIRMED: 控制脚本日志提供直接证据 → 自动化误报
    - NO_DEVICE_ANOMALY_FOUND:         板端证据不支持产品故障（不＝自动化误报）
    - DEVICE_EVIDENCE_INCOMPLETE:      板端证据不足以判断
    - MULTIPLE_POSSIBLE_CAUSES:        多条候选根因,无法收敛
    """

    DEVICE_FAILURE_CONFIRMED = "DEVICE_FAILURE_CONFIRMED"
    ENVIRONMENT_FAILURE_INDICATED = "ENVIRONMENT_FAILURE_INDICATED"
    TEST_AUTOMATION_FAILURE_CONFIRMED = "TEST_AUTOMATION_FAILURE_CONFIRMED"
    NO_DEVICE_ANOMALY_FOUND = "NO_DEVICE_ANOMALY_FOUND"
    DEVICE_EVIDENCE_INCOMPLETE = "DEVICE_EVIDENCE_INCOMPLETE"
    MULTIPLE_POSSIBLE_CAUSES = "MULTIPLE_POSSIBLE_CAUSES"


# ============================================================
# Confidence 等级
# ============================================================
CONFIDENCE_LEVELS = ("low", "medium", "high")


# ============================================================
# CLI 入口请求
# ============================================================
class RunRequest(BaseModel):
    """CLI analyze 命令接受的最小请求结构。

    必需: evb_log_path, output_dir
    可选: control_log_path / label / thread_id / overwrite
    不接受: loop 编号（plan §1 R1）
    """

    model_config = ConfigDict(extra="forbid")

    evb_log_path: str = Field(..., description="已切分好的单次 EVB 日志路径")
    output_dir: str = Field(..., description="报告输出目录")
    control_log_path: str | None = Field(default=None, description="可选控制脚本日志路径")
    label: str | None = Field(default=None, description="用户自定义标识（loop/case 等）")
    thread_id: str | None = Field(default=None, description="LangGraph thread id")
    overwrite: bool = Field(default=False, description="是否允许覆盖已有产物")


# ============================================================
# 证据索引与引用
# ============================================================
class EvidenceRef(BaseModel):
    """原始日志证据的稳定引用。

    字段:
      - ref_id:  在 analysis.json 内唯一的证据 ID, 例如 "EV-0001"
      - source:  来源文件名（仅显示,不带绝对路径）
      - line_no: 原始行号（若存在）
      - timestamp:  设备/采集时间（若可解析）
      - raw_text: 原始日志文本（可本地保真;trace/终端不展示完整敏感值）
      - module:   模块名(ap/apc1/sensor 等)
    """

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    source: str
    line_no: int | None = None
    timestamp: str | None = None
    raw_text: str
    module: str | None = None


# ============================================================
# 时间线事件
# ============================================================
class TimelineEvent(BaseModel):
    """失败时间线中的单个事件。

    字段:
      - ts:    时间戳字符串（可缺失,如只有相对时间）
      - event: 一句话描述
      - ref_id: 指向 EvidenceRef.ref_id
      - source_module:  来源模块
      - kind:       事件类型 (command/failure/recovery/success/omitted_summary/ping_burst 等)
                    可选; 由 renderer 与 validator 共享语义。
      - step_label:  所属测试步骤标签 (如 "ping"/"sms"); 与 EvidenceBlock.step_label 对齐。
      - is_failure_step: 是否为故障步 (出问题的那一步)。脊椎标记。
    """

    model_config = ConfigDict(extra="forbid")

    ts: str | None = None
    event: str
    ref_id: str
    source_module: str | None = None
    kind: str | None = None
    step_label: str | None = None
    is_failure_step: bool = False


# ============================================================
# 设备 log 证据分块 (Timeline Spine)
# ============================================================
class EvidenceBlock(BaseModel):
    """按测试步骤组织的设备 log 证据分块。

    字段:
      - step_label:        测试步骤标签 (与 TimelineEvent.step_label 对齐)
      - is_failure_step:   是否故障步块 (故障步块更详, 含前后对照)
      - role:              块角色: "main" | "before" | "after"
                          - main: 故障/步骤主块
                          - before: 故障步前对照
                          - after:  故障步后对照
      - ref_ids:           引用的 EvidenceRef.ref_id 列表 (仅设备侧)
                          控制脚本来源的 ref 不得进入此列表。
    """

    model_config = ConfigDict(extra="forbid")

    step_label: str
    is_failure_step: bool = False
    role: str = "main"
    ref_ids: list[str] = Field(default_factory=list)


# ============================================================
# 根因链节点
# ============================================================
class CausalChainLink(BaseModel):
    """根因链中的一个节点。

    字段:
      - role: "trigger" | "propagation" | "terminal_impact"
      - description: 一句话描述
      - ref_ids:  支撑该节点的 evidence refs
      - gap:      当证据不足时填写说明（plan R12: 不得补造事件）
    """

    model_config = ConfigDict(extra="forbid")

    role: str
    description: str
    ref_ids: list[str] = Field(default_factory=list)
    gap: str | None = None


# ============================================================
# 顶层结果
# ============================================================
class AnalysisResult(BaseModel):
    """诊断产物的最终结构化结果。

    注意: 这是单一 SSOT。report.md 由确定性 renderer 从本结构渲染。
    模型不得直接写文件 (Plan §1, §2 S13)。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_label: str = Field(default="单次测试执行")
    classification: Classification
    root_cause_confidence: str = Field(default="low", description="low/medium/high")

    scenario: str | None = Field(default=None, description="推断出的测试场景")
    scenario_confidence: str | None = Field(default=None)

    first_anomaly: dict[str, Any] | None = Field(
        default=None,
        description="首个异常步骤的最小表示: {step, ref_id, summary}",
    )

    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    root_cause_chain: list[CausalChainLink] = Field(default_factory=list)

    # ------------------------------------------------------------
    # Timeline Spine 字段 (Plan 2026-07-21-002). 全部可选, 向后兼容。
    # ------------------------------------------------------------
    flow_one_liner: str | None = Field(
        default=None,
        description="一行短流程摘要, 例如 'Data 检查 -> ping -> SMS' (R4/S1)",
    )
    confirmed_impact: str | None = Field(
        default=None,
        description="已确认的现象/影响 (R2/S1); 低置信时领口先陈述此字段。",
    )
    suspected_root_cause: str | None = Field(
        default=None,
        description="疑似根因 (R2/S1); 低置信时须用「疑似」措辞。",
    )
    evidence_blocks: list[EvidenceBlock] = Field(
        default_factory=list,
        description="按测试步骤组织的设备 log 证据分块 (R9-R12/S4); 控制脚本源不得进入。",
    )

    control_log_used: bool = Field(
        default=False,
        description="是否使用了控制脚本日志(用于解释 TEST_AUTOMATION_FAILURE_CONFIRMED 的来源)",
    )
    external_result: str = Field(default="FAIL", description="外部测试结果(默认 FAIL)")

    notes: list[str] = Field(default_factory=list, description="剩余不确定性 / 边界说明")
    suggested_actions: list[str] = Field(default_factory=list)


__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "Classification",
    "CONFIDENCE_LEVELS",
    "RunRequest",
    "EvidenceRef",
    "TimelineEvent",
    "EvidenceBlock",
    "CausalChainLink",
    "AnalysisResult",
]
