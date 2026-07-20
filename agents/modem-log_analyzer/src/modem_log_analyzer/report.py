"""ModemLogAnalyzer —— 确定性 report.md / analysis.json 渲染 (Unit 6)。

按 Plan §5 Unit 6:
  - 从 AnalysisResult dict 渲染两种产物, 不调用 LLM。
  - 章节顺序固定 (Plan R19):
      1. 失败概览
      2. 推断的测试场景与基线
      3. 核心诊断
      4. 根因链
      5. 失败时间线
      6. 测试步骤与日志证据
      7. 故障域判定与推理
      8. 剩余不确定性
      9. 建议行动
     10. 正式证据索引
  - 原子写入: 临时文件 + os.replace (Plan §1: "原子提交")。
  - 终端摘要: 不回显原文(可能含号码/IMSI/ICCID); 只显示分类 + ref_id 列表。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


# ============================================================
# 报告章节顺序 (Plan R19) - 锁定
# ============================================================
REPORT_SECTIONS = [
    "失败概览",
    "推断的测试场景与基线",
    "核心诊断",
    "根因链",
    "失败时间线",
    "测试步骤与日志证据",
    "故障域判定与推理",
    "剩余不确定性",
    "建议行动",
    "正式证据索引",
]


# ============================================================
# 校验
# ============================================================
_VALID_REF_IDS_IN_INDEX = re.compile(r"^EV-\d{4,}$")


def _validate_evidence_refs(result: dict) -> None:
    """校验 result 中的 ref_ids 全部在 evidence_refs 列表里。"""
    valid = {e["ref_id"] for e in result.get("evidence_refs") or []}
    # first_anomaly 引用必须有效
    fa = result.get("first_anomaly") or {}
    if fa and fa.get("ref_id"):
        if fa["ref_id"] not in valid:
            raise ValueError(
                f"first_anomaly references unknown ref_id: {fa['ref_id']!r}; "
                f"valid: {sorted(valid)}"
            )
    # root_cause_chain 引用必须有效
    for link in result.get("root_cause_chain") or []:
        for rid in link.get("ref_ids") or []:
            if rid not in valid:
                raise ValueError(
                    f"root_cause_chain link references unknown ref_id: {rid!r}; "
                    f"valid: {sorted(valid)}"
                )


# ============================================================
# report.md 渲染
# ============================================================
def render_report_md(result: dict[str, Any]) -> str:
    """把 AnalysisResult dict 渲染成中文 Markdown 报告。"""
    _validate_evidence_refs(result)

    sections: list[str] = []
    sections.append(_render_failure_overview(result))
    sections.append(_render_scenario(result))
    sections.append(_render_core_diagnosis(result))
    sections.append(_render_root_cause_chain(result))
    sections.append(_render_timeline(result))
    sections.append(_render_steps_and_evidence(result))
    sections.append(_render_classification_reasoning(result))
    sections.append(_render_uncertainties(result))
    sections.append(_render_actions(result))
    sections.append(_render_evidence_index(result))

    return "\n\n".join(sections) + "\n"


def _render_failure_overview(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    confidence = result.get("root_cause_confidence", "low")
    run_label = result.get("run_label", "单次测试执行")
    external = result.get("external_result", "FAIL")
    scenario = result.get("scenario") or "(未推断)"
    scenario_conf = result.get("scenario_confidence") or "n/a"

    return (
        "# 失败概览\n\n"
        f"- **运行标识**: {run_label}\n"
        f"- **外部测试结果**: `{external}`\n"
        f"- **推断场景**: {scenario} (置信度: {scenario_conf})\n"
        f"- **诊断分类**: `{classification}`\n"
        f"- **根因置信度**: `{confidence}`\n"
    )


def _render_scenario(result: dict) -> str:
    scenario = result.get("scenario") or "(未推断)"
    scenario_conf = result.get("scenario_confidence") or "n/a"
    business_actions: list[str] = []
    # 从 timeline / evidence 推断动作
    for ev in result.get("evidence_refs") or []:
        text = ev.get("raw_text", "")
        if "debug_bes_rpc 1" in text:
            business_actions.append("Call")
        elif "debug_bes_rpc 3" in text:
            business_actions.append("SMS")
        elif "!ping" in text or "!ping6" in text:
            business_actions.append("Data/Ping")
        elif "!ifconfig" in text:
            business_actions.append("Setting")
    return (
        "# 推断的测试场景与基线\n\n"
        f"- **场景**: {scenario}\n"
        f"- **场景置信度**: {scenario_conf}\n"
        f"- **识别到的业务动作**: {', '.join(sorted(set(business_actions))) or '(未识别)'}\n"
        "- **验收条件**: 由 Agent 根据命令序列推断, 详见 `core_diagnosis` 与 `timeline` 章节。\n"
        "- **来源**: 自动推断 (用户提供 case 描述时本节会显示用户提供)。\n"
    )


def _render_core_diagnosis(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    fa = result.get("first_anomaly")
    if fa:
        return (
            "# 核心诊断\n\n"
            f"- **分类**: `{classification}`\n"
            f"- **首个异常步骤**: 行 {fa.get('line_no')} / {fa.get('ref_id')} "
            f"(模块={fa.get('module') or '-'}; ts={fa.get('ts') or '-'})\n"
            f"- **最可能原因**: {fa.get('summary', '(未描述)')}\n"
            f"- **直接影响**: 业务状态流中断, 触发外部 FAIL。\n"
            "- **结论边界**: 仅基于 EVB 日志; 控制脚本日志可补充或反驳此结论 (见 R10/R16)。\n"
        )
    return (
        "# 核心诊断\n\n"
        f"- **分类**: `{classification}`\n"
        "- **已验证的关键状态**: 板端业务动作正常, 回调 OK, 未发现 ERROR/FAIL 关键字。\n"
        "- **缺失证据**: 终端事件、外部断言、控制脚本侧错误 (Unit 5 interrupt 已请求)。\n"
        "- **结论边界**: 仅 EVB 日志无法解释外部 FAIL, 需控制脚本日志确认是否自动化误报。\n"
    )


def _render_root_cause_chain(result: dict) -> str:
    chain = result.get("root_cause_chain") or []
    if not chain:
        return (
            "# 根因链\n\n"
            "- 未发现板端异常, 无根因链可构造。\n"
            "- **缺口**: 控制脚本日志缺失; 若后续提供, 链可重建。\n"
        )
    lines = ["# 根因链\n"]
    for link in chain:
        role = link.get("role", "?")
        desc = link.get("description", "(未描述)")
        ref_ids = link.get("ref_ids") or []
        gap = link.get("gap")
        ref_str = ", ".join(ref_ids) if ref_ids else "(无)"
        lines.append(f"- **{role}**: {desc}  \n  证据: {ref_str}")
        if gap:
            lines.append(f"  - 缺口: {gap}")
    return "\n".join(lines)


def _render_timeline(result: dict) -> str:
    timeline = result.get("timeline") or []
    if not timeline:
        return "# 失败时间线\n\n- 无时间线事件 (板端无业务动作或全部为 noise)。\n"
    lines = ["# 失败时间线\n"]
    for ev in timeline:
        ts = ev.get("ts") or "-"
        desc = ev.get("event", "")
        ref = ev.get("ref_id") or "-"
        mod = ev.get("source_module") or "-"
        lines.append(f"- `{ts}` [{mod}] {desc}  \n  证据: {ref}")
    return "\n".join(lines)


def _render_steps_and_evidence(result: dict) -> str:
    refs = result.get("evidence_refs") or []
    if not refs:
        return "# 测试步骤与日志证据\n\n- 无 evidence_refs。\n"
    lines = ["# 测试步骤与日志证据\n"]
    for ev in refs:
        rid = ev.get("ref_id")
        ln = ev.get("line_no")
        ts = ev.get("timestamp") or "-"
        mod = ev.get("module") or "-"
        text = ev.get("raw_text") or ""
        lines.append(
            f"- `{rid}` (行 {ln}, 模块={mod}, ts={ts}):\n"
            f"  ```\n  {text}\n  ```"
        )
    return "\n".join(lines)


def _render_classification_reasoning(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    external = result.get("external_result", "FAIL")
    control_used = result.get("control_log_used", False)
    text = (
        "# 故障域判定与推理\n\n"
        f"- **外部测试结果**: `{external}` (与 Agent 故障归因**分离**, Plan §1 R13/R14)。\n"
        f"- **Agent 诊断分类**: `{classification}`\n"
        f"- **控制脚本日志**: {'已使用' if control_used else '未提供 / 未使用'}\n"
        "- **推理**: 依据 ``decide_classification`` 决策矩阵 (R13); 仅 EVB 日志不得宣称自动化误报; "
        "TEST_AUTOMATION_FAILURE_CONFIRMED 必须有控制脚本侧直接证据。\n"
    )
    return text


def _render_uncertainties(result: dict) -> str:
    notes = result.get("notes") or []
    if not notes:
        return "# 剩余不确定性\n\n- 未列出额外不确定性。\n"
    lines = ["# 剩余不确定性\n"]
    for n in notes:
        lines.append(f"- {n}")
    return "\n".join(lines)


def _render_actions(result: dict) -> str:
    actions = result.get("suggested_actions") or []
    if not actions:
        return "# 建议行动\n\n- 未列出建议。\n"
    lines = ["# 建议行动\n"]
    for a in actions:
        lines.append(f"- {a}")
    return "\n".join(lines)


def _render_evidence_index(result: dict) -> str:
    refs = result.get("evidence_refs") or []
    if not refs:
        return "# 正式证据索引\n\n- (空)\n"
    lines = ["# 正式证据索引\n", "| 证据 ID | 来源 | 行号 | 模块 | 时间戳 |", "| --- | --- | --- | --- | --- |"]
    for ev in refs:
        rid = ev.get("ref_id")
        src = ev.get("source")
        ln = ev.get("line_no")
        mod = ev.get("module") or "-"
        ts = ev.get("timestamp") or "-"
        lines.append(f"| `{rid}` | {src} | {ln} | {mod} | {ts} |")
    lines.append("\n> 本节是报告其它章节中所有 `EV-NNNN` 引用的真相之源。")
    return "\n".join(lines)


# ============================================================
# analysis.json 序列化
# ============================================================
def render_analysis_json(result: dict[str, Any]) -> str:
    """把 AnalysisResult dict 序列化为 JSON 字符串。

    使用 ensure_ascii=False 保留中文字符; indent=2 便于人工 diff。
    """
    _validate_evidence_refs(result)
    # 不写入 _meta (内部字段)
    payload = {k: v for k, v in result.items() if not k.startswith("_")}
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


# ============================================================
# 终端摘要
# ============================================================
_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{10,}\b")
_IMSI_RE = re.compile(r"\b460\d{10,}\b")


def _redact_phone_digits(text: str) -> str:
    """遮蔽电话号码/长数字串(Plan §1 隐私)。"""
    if not text:
        return text
    text = _IMSI_RE.sub("[IMSI]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _LONG_DIGITS_RE.sub("[REDACTED]", text)
    return text


def render_terminal_summary(result: dict[str, Any]) -> str:
    """渲染终端摘要: 分类 + ref_id 列表 + 简短 note。不回显原文。"""
    classification = result.get("classification", "UNKNOWN")
    confidence = result.get("root_cause_confidence", "low")
    scenario = result.get("scenario") or "(未推断)"
    ref_count = len(result.get("evidence_refs") or [])
    first_anomaly = result.get("first_anomaly") or {}
    fa_line = ""
    if first_anomaly:
        fa_line = f"\n首个异常: 行 {first_anomaly.get('line_no')} / {first_anomaly.get('ref_id')} (模块={first_anomaly.get('module') or '-'})"

    ref_ids = [e.get("ref_id") for e in (result.get("evidence_refs") or [])]
    ref_ids_str = ", ".join(ref_ids[:8]) + (" ..." if len(ref_ids) > 8 else "")

    notes_count = len(result.get("notes") or [])

    return (
        f"[modem-log-analyzer] classification={classification} confidence={confidence}\n"
        f"scenario: {_redact_phone_digits(scenario)}{fa_line}\n"
        f"evidence refs ({ref_count}): {ref_ids_str}\n"
        f"notes: {notes_count} item(s)\n"
    )


# ============================================================
# 原子写入
# ============================================================
def atomic_write_artifacts(
    *,
    result: dict[str, Any],
    output_dir: str,
    overwrite: bool,
) -> None:
    """原子写入 report.md + analysis.json 到 output_dir。

    流程:
      1. 校验 evidence refs
      2. 渲染两种产物到内存
      3. 写到临时文件 (report.md.tmp / analysis.json.tmp)
      4. 检查 overwrite 规则
      5. os.replace 到正式文件
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md = render_report_md(result)
    js = render_analysis_json(result)

    # 覆盖保护: 已有正式文件时不替换(除非 overwrite)
    if not overwrite:
        if (out / "report.md").exists() or (out / "analysis.json").exists():
            raise FileExistsError(
                f"refusing to overwrite existing artifacts in {out}; use overwrite=True"
            )

    # 写临时文件 + 原子替换
    md_tmp = out / "report.md.tmp"
    js_tmp = out / "analysis.json.tmp"
    md_final = out / "report.md"
    js_final = out / "analysis.json"

    try:
        md_tmp.write_text(md, encoding="utf-8")
        js_tmp.write_text(js, encoding="utf-8")
        os.replace(md_tmp, md_final)
        os.replace(js_tmp, js_final)
    except Exception:
        # 清理临时文件
        for p in (md_tmp, js_tmp):
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        raise


__all__ = [
    "REPORT_SECTIONS",
    "render_report_md",
    "render_analysis_json",
    "render_terminal_summary",
    "atomic_write_artifacts",
]