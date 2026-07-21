"""ModemLogAnalyzer —— 确定性 report.md / analysis.json 渲染 (Unit 6)。

按 Plan §5 Unit 6:
  - 从 AnalysisResult dict 渲染两种产物, 不调用 LLM。
  - 章节顺序固定 (Plan R19)。
  - 可读性优先: 时间线/证据只展示关键条目; 完整索引留在 analysis.json。
  - 原子写入: 临时文件 + os.replace。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

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


def _validate_evidence_refs(result: dict) -> None:
    valid = {e["ref_id"] for e in result.get("evidence_refs") or []}
    fa = result.get("first_anomaly") or {}
    if fa and fa.get("ref_id"):
        if fa["ref_id"] not in valid:
            raise ValueError(
                f"first_anomaly references unknown ref_id: {fa['ref_id']!r}; valid: {sorted(valid)}"
            )
    for link in result.get("root_cause_chain") or []:
        for rid in link.get("ref_ids") or []:
            if rid not in valid:
                raise ValueError(
                    f"root_cause_chain link references unknown ref_id: {rid!r}; "
                    f"valid: {sorted(valid)}"
                )


def render_report_md(result: dict[str, Any]) -> str:
    _validate_evidence_refs(result)

    sections: list[str] = [
        _render_failure_overview(result),
        _render_scenario(result),
        _render_core_diagnosis(result),
        _render_root_cause_chain(result),
        _render_timeline(result),
        _render_steps_and_evidence(result),
        _render_classification_reasoning(result),
        _render_uncertainties(result),
        _render_actions(result),
        _render_evidence_index(result),
    ]

    return "\n\n".join(sections) + "\n"


def _render_failure_overview(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    confidence = result.get("root_cause_confidence", "low")
    run_label = result.get("run_label", "单次测试执行")
    external = result.get("external_result", "FAIL")
    scenario = result.get("scenario") or "(未推断)"
    scenario_conf = result.get("scenario_confidence") or "n/a"
    control = "是" if result.get("control_log_used") else "否"

    return (
        "## 失败概览\n\n"
        f"- **运行标识**: {run_label}\n"
        f"- **外部测试结果**: `{external}`\n"
        f"- **推断场景**: {scenario} (置信度: {scenario_conf})\n"
        f"- **诊断分类**: `{classification}`\n"
        f"- **根因置信度**: `{confidence}`\n"
        f"- **是否使用控制脚本日志**: {control}\n"
    )


def _render_scenario(result: dict) -> str:
    scenario = result.get("scenario") or "(未推断)"
    scenario_conf = result.get("scenario_confidence") or "n/a"
    actions = result.get("business_actions") or []
    if not actions:
        # 兼容旧结果: 从 timeline / evidence 里猜 (正确 RPC 组)
        actions = _infer_actions_fallback(result)
    return (
        "## 推断的测试场景与基线\n\n"
        f"- **场景**: {scenario}\n"
        f"- **场景置信度**: {scenario_conf}\n"
        f"- **识别到的业务动作**: {', '.join(actions) or '(未识别)'}\n"
        "- **验收条件**: 由命令序列自动推断; 以「核心诊断」与精简时间线为准。\n"
        "- **来源**: 自动推断。\n"
    )


def _infer_actions_fallback(result: dict) -> list[str]:
    found: list[str] = []
    texts = " ".join(
        (e.get("raw_text") or "") + " " + (e.get("event") or "")
        for e in (result.get("evidence_refs") or []) + (result.get("timeline") or [])
    )
    checks = [
        ("debug_bes_rpc 0", "Call"),
        ("debug_bes_rpc 4", "SMS"),
        ("!ping", "Data/Ping"),
        ("!ping6", "Data/Ping"),
        ("debug_bes_rpc 1", "Data/Ping"),
        ("!ifconfig", "Setting"),
    ]
    for needle, label in checks:
        if needle in texts and label not in found:
            found.append(label)
    return found


def _render_core_diagnosis(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    fa = result.get("first_anomaly")
    control_used = bool(result.get("control_log_used"))
    ctrl_items = result.get("control_evidence") or []

    lines = ["## 核心诊断\n", f"- **分类**: `{classification}`"]
    if fa:
        lines.append(
            f"- **首个板端异常**: 行 {fa.get('line_no')} / `{fa.get('ref_id')}` "
            f"(模块={fa.get('module') or '-'}; ts={fa.get('ts') or '-'})"
        )
        lines.append(f"- **异常摘要**: {fa.get('summary', '(未描述)')}")
        lines.append("- **直接影响**: 该步骤偏离预期, 与外部 FAIL 时间线相关。")
    else:
        lines.append("- **板端异常**: 未发现明确 ERROR/FAIL/超时类信号。")

    if ctrl_items:
        lines.append("- **控制脚本要点**:")
        for item in ctrl_items[:5]:
            ln = item.get("line_no")
            lines.append(f"  - 行 {ln}: {item.get('summary')}")
    elif control_used:
        lines.append("- **控制脚本要点**: 已提供控制日志, 但未匹配到断言/FAIL 类直接证据。")
    else:
        lines.append("- **控制脚本要点**: 未提供。")

    if control_used:
        lines.append(
            "- **结论边界**: 同时参考了 EVB 与控制脚本; 分类不得把外部 FAIL 直接等同板端产品故障。"
        )
    else:
        lines.append(
            "- **结论边界**: 仅基于 EVB; 控制脚本可补充或反驳此结论。"
        )
    return "\n".join(lines) + "\n"


def _render_root_cause_chain(result: dict) -> str:
    chain = result.get("root_cause_chain") or []
    if not chain:
        return (
            "## 根因链\n\n"
            "- 未构造根因链 (板端无首异常且控制侧无直接证据)。\n"
        )
    lines = ["## 根因链\n"]
    for link in chain:
        role = link.get("role", "?")
        desc = link.get("description", "(未描述)")
        ref_ids = link.get("ref_ids") or []
        gap = link.get("gap")
        ref_str = ", ".join(f"`{r}`" for r in ref_ids) if ref_ids else "—"
        lines.append(f"- **{role}**: {desc}")
        lines.append(f"  - 证据: {ref_str}")
        if gap:
            lines.append(f"  - 缺口: {gap}")
    return "\n".join(lines)


def _render_timeline(result: dict) -> str:
    timeline = result.get("timeline") or []
    if not timeline:
        return "## 失败时间线\n\n- 无关键业务事件。\n"

    lines = [
        "## 失败时间线\n",
        "> 仅列出命令与明确成败回调; 噪声行已省略。\n",
    ]
    for ev in timeline:
        if ev.get("kind") == "omitted_summary":
            lines.append(f"- _{ev.get('event')}_")
            continue
        ts = ev.get("ts") or "—"
        desc = ev.get("event", "")
        ref = ev.get("ref_id")
        mod = ev.get("source_module")
        meta = []
        if mod:
            meta.append(str(mod))
        if ref:
            meta.append(f"`{ref}`")
        suffix = f"  ({', '.join(meta)})" if meta else ""
        lines.append(f"- `{ts}` {desc}{suffix}")
    return "\n".join(lines)


def _cited_ref_ids(result: dict) -> set[str]:
    """报告正文真正引用到的 evidence id (不含合并 ping 噪声)。"""
    cited: set[str] = set()
    fa = result.get("first_anomaly") or {}
    if fa.get("ref_id"):
        cited.add(fa["ref_id"])
    for link in result.get("root_cause_chain") or []:
        for rid in link.get("ref_ids") or []:
            cited.add(rid)
    for ev in result.get("timeline") or []:
        kind = ev.get("kind")
        if kind in {"omitted_summary", "ping_burst"}:
            continue
        # 时间线里的失败回调 + 命令才进正文证据
        if kind == "command" and ev.get("ref_id"):
            cited.add(ev["ref_id"])
        event = (ev.get("event") or "")
        if ev.get("ref_id") and ("失败" in event or "No response" in event or "ERROR" in event):
            cited.add(ev["ref_id"])
    return cited


def _render_steps_and_evidence(result: dict) -> str:
    refs = result.get("evidence_refs") or []
    if not refs:
        return "## 测试步骤与日志证据\n\n- 无 evidence_refs。\n"

    by_id = {r.get("ref_id"): r for r in refs if r.get("ref_id")}
    cited = _cited_ref_ids(result)

    # 额外纳入: 看起来像命令的证据行 (modemcli / debug_bes_rpc / !ping)
    for r in refs:
        text = r.get("raw_text") or ""
        if any(k in text for k in ("debug_bes_rpc", "!ping", "!ifconfig", "!ping6")):
            if r.get("ref_id"):
                cited.add(r["ref_id"])

    # 保序
    ordered = [r for r in refs if r.get("ref_id") in cited]
    omitted = len(refs) - len(ordered)

    lines = [
        "## 测试步骤与日志证据\n",
        f"> 展示 {len(ordered)} 条关键证据"
        + (f"（另有 {omitted} 条噪声/次要行仅存于 analysis.json）" if omitted else "")
        + "。\n",
    ]
    for ev in ordered:
        rid = ev.get("ref_id")
        ln = ev.get("line_no")
        ts = ev.get("timestamp") or "—"
        mod = ev.get("module") or "—"
        text = _clip_raw(ev.get("raw_text") or "")
        lines.append(f"- `{rid}` (行 {ln}, {mod}, {ts}):")
        lines.append(f"  ```\n  {text}\n  ```")
    return "\n".join(lines)


def _clip_raw(text: str, *, max_len: int = 240) -> str:
    t = text.strip()
    if "\t" in t:
        # merge.log: 显示板端侧, 保留可读性
        t = t.split("\t", 1)[-1].strip()
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _render_classification_reasoning(result: dict) -> str:
    classification = result.get("classification", "UNKNOWN")
    external = result.get("external_result", "FAIL")
    control_used = result.get("control_log_used", False)
    ctrl_n = len(result.get("control_evidence") or [])
    return (
        "## 故障域判定与推理\n\n"
        f"- **外部测试结果**: `{external}`（与诊断分类分离）\n"
        f"- **诊断分类**: `{classification}`\n"
        f"- **控制脚本日志**: {'已使用' if control_used else '未提供'}"
        + (f"（直接证据 {ctrl_n} 条）" if control_used else "")
        + "\n"
        "- **规则要点**: `TEST_AUTOMATION_FAILURE_CONFIRMED` 仅在控制侧有直接证据且"
        "板端无产品异常时可确认; 仅 EVB 不得宣称自动化误报。\n"
    )


def _render_uncertainties(result: dict) -> str:
    notes = result.get("notes") or []
    if not notes:
        return "## 剩余不确定性\n\n- 无额外不确定性记录。\n"
    lines = ["## 剩余不确定性\n"]
    for n in notes:
        lines.append(f"- {n}")
    return "\n".join(lines)


def _render_actions(result: dict) -> str:
    actions = result.get("suggested_actions") or []
    if not actions:
        return "## 建议行动\n\n- 无额外建议。\n"
    lines = ["## 建议行动\n"]
    for a in actions:
        lines.append(f"- {a}")
    return "\n".join(lines)


def _render_evidence_index(result: dict) -> str:
    refs = result.get("evidence_refs") or []
    if not refs:
        return "## 正式证据索引\n\n- (空)\n"

    cited = _cited_ref_ids(result)
    for r in refs:
        text = r.get("raw_text") or ""
        if any(k in text for k in ("debug_bes_rpc", "!ping", "!ifconfig", "!ping6")):
            if r.get("ref_id"):
                cited.add(r["ref_id"])

    key_refs = [r for r in refs if r.get("ref_id") in cited]
    omitted = len(refs) - len(key_refs)

    lines = [
        "## 正式证据索引\n",
        f"> 关键引用 {len(key_refs)} 条"
        + (f"; 完整 {len(refs)} 条见同目录 `analysis.json`" if omitted else "")
        + "。\n",
        "| 证据 ID | 来源 | 行号 | 模块 | 时间戳 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for ev in key_refs:
        rid = ev.get("ref_id")
        src = ev.get("source")
        ln = ev.get("line_no")
        mod = ev.get("module") or "—"
        ts = ev.get("timestamp") or "—"
        lines.append(f"| `{rid}` | {src} | {ln} | {mod} | {ts} |")
    return "\n".join(lines)


def render_analysis_json(result: dict[str, Any]) -> str:
    _validate_evidence_refs(result)
    # 保留 ``_meta`` (runner / interrupt / backend 证明); 其它 ``_`` 私有键仍剥离
    payload = {k: v for k, v in result.items() if not k.startswith("_")}
    meta = result.get("_meta")
    if meta is not None:
        payload["_meta"] = meta
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{10,}\b")
_IMSI_RE = re.compile(r"\b460\d{10,}\b")


def _redact_phone_digits(text: str) -> str:
    if not text:
        return text
    text = _IMSI_RE.sub("[IMSI]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _LONG_DIGITS_RE.sub("[REDACTED]", text)
    return text


def render_terminal_summary(result: dict[str, Any]) -> str:
    classification = result.get("classification", "UNKNOWN")
    confidence = result.get("root_cause_confidence", "low")
    scenario = result.get("scenario") or "(未推断)"
    ref_count = len(result.get("evidence_refs") or [])
    timeline_n = len(
        [t for t in (result.get("timeline") or []) if t.get("kind") != "omitted_summary"]
    )
    first_anomaly = result.get("first_anomaly") or {}
    fa_line = ""
    if first_anomaly:
        fa_line = (
            f"\n首个异常: 行 {first_anomaly.get('line_no')} / "
            f"{first_anomaly.get('ref_id')} "
            f"(模块={first_anomaly.get('module') or '-'})"
        )

    cited = sorted(_cited_ref_ids(result))
    ref_ids_str = ", ".join(cited[:8]) + (" ..." if len(cited) > 8 else "")

    notes_count = len(result.get("notes") or [])

    return (
        f"[modem-log-analyzer] classification={classification} confidence={confidence}\n"
        f"scenario: {_redact_phone_digits(scenario)}{fa_line}\n"
        f"timeline events: {timeline_n}; evidence total: {ref_count}; "
        f"cited: {ref_ids_str or '(none)'}\n"
        f"notes: {notes_count} item(s)\n"
    )


def atomic_write_artifacts(
    *,
    result: dict[str, Any],
    output_dir: str,
    overwrite: bool,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md = render_report_md(result)
    js = render_analysis_json(result)

    if not overwrite:
        if (out / "report.md").exists() or (out / "analysis.json").exists():
            raise FileExistsError(
                f"refusing to overwrite existing artifacts in {out}; use overwrite=True"
            )

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
