"""ModemLogAnalyzer —— AnalysisService (Unit 4 端到端)。

按 Plan Unit 4:
  - 入口: ``run_analyze(evb_log_path, output_dir, ...)`` 返回 AnalysisResult dict。
  - 流程:
      1. intake 验证(由 CLI 调用方负责, 这里假设已通过)
      2. log_parser.parse_evb_log → 事件列表
      3. evidence.build_evidence_index → refs
      4. scenario_inference.infer_scenario → 推断场景
      5. classification.find_first_anomaly → 首异常
      6. classification.decide_classification → 顶层分类
      7. 构造 AnalysisResult dict (符合 contracts.AnalysisResult schema)
  - 接口契约: dict[str, Any], 字段名稳定, 便于 Unit 6 渲染。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from modem_log_analyzer.classification import (
    compute_root_cause_confidence,
    decide_classification,
    find_first_anomaly,
)
from modem_log_analyzer.contracts import (
    ANALYSIS_SCHEMA_VERSION,
)
from modem_log_analyzer.control_log_policy import (
    build_interrupt_request,
    has_direct_automation_evidence,
    parse_control_log,
    should_request_control_log,
)
from modem_log_analyzer.evidence import build_evidence_index
from modem_log_analyzer.log_parser import parse_evb_log
from modem_log_analyzer.scenario_inference import infer_scenario


class AnalysisService:
    """Unit 4 真实分析服务。

    Unit 1 占位实现已被替换为完整管线。
    后续 Unit 5/6 在此基础上接入 interrupt/resume 与产物落盘。
    """

    def run_analyze(
        self,
        *,
        evb_log_path: str,
        output_dir: str,
        control_log_path: str | None = None,
        label: str | None = None,
        thread_id: str | None = None,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        # 1. 读取 EVB 日志
        path = Path(evb_log_path)
        raw_text = path.read_text(encoding="utf-8", errors="replace")

        # 2. 解析
        events = parse_evb_log(raw_text)

        # 2.5 控制日志(若提供且文件存在)
        control_events: list[dict] = []
        if control_log_path:
            cpath = Path(control_log_path)
            if cpath.exists() and cpath.is_file():
                try:
                    ctext = cpath.read_text(encoding="utf-8", errors="replace")
                    control_events = parse_control_log(ctext)
                except Exception:
                    # 读取失败不应让 analyze 整体失败; 视为无 control_log
                    control_events = []
            else:
                # 文件不存在或不可读: 不报错, has_control_log 保持 False
                control_log_path = None
                has_control_log = False

        # 3. 证据索引
        evidence_refs = build_evidence_index(events, source=path.name)

        # 4. 场景推断
        scenario_obj = infer_scenario(events)
        scenario = scenario_obj["name"] if scenario_obj else None
        scenario_confidence = scenario_obj["confidence"] if scenario_obj else None

        # 5. 首异常
        first_anomaly = find_first_anomaly(events, evidence_refs)

        # 6. 顶层分类决策
        has_device_anomaly = first_anomaly is not None
        has_environment_evidence = False  # Unit 4 阶段尚未区分环境指征
        # 用户是否提供了控制日志路径(用于 interrupt 决策)
        has_control_log = control_log_path is not None
        # has_control_log_evidence: 必须有直接证据(Plan R16); 仅"路径存在"不够
        has_direct_evidence = bool(control_events) and has_direct_automation_evidence(
            control_events
        )
        # 完整: 有 first_anomaly + 至少一个 callback/response, 或干净日志至少 1 个 evidence
        has_followup = any(ev.get("kind") in ("callback", "response") for ev in events)
        is_complete = (first_anomaly is not None and has_followup) or (
            first_anomaly is None and len(evidence_refs) >= 1
        )
        classification_enum = decide_classification(
            has_device_anomaly=has_device_anomaly,
            has_environment_evidence=has_environment_evidence,
            has_control_log_evidence=has_direct_evidence,
            is_complete=is_complete,
        )

        # 6.5 Unit 5: 控制日志 evidence 已用于上一步, 不再二次升级。

        # 7. 置信度
        n_supporting = len(evidence_refs) if first_anomaly else 0
        n_gaps = 0 if first_anomaly else max(0, 3 - len(evidence_refs))
        root_cause_confidence = compute_root_cause_confidence(
            n_supporting_refs=n_supporting,
            n_gaps=n_gaps,
            classification=classification_enum,
        )

        # 8. 时间线 + 根因链 + 控制侧关键证据
        # 先缩短首异常摘要, 再入根因链 (避免链里塞整行双时间戳)
        if first_anomaly and first_anomaly.get("summary"):
            first_anomaly = {
                **first_anomaly,
                "summary": _shorten_log_snippet(first_anomaly["summary"]),
            }

        timeline = _build_timeline(events, evidence_refs)
        control_evidence = _control_evidence_items(control_events)
        root_cause_chain = _build_root_cause_chain(
            first_anomaly,
            evidence_refs,
            control_evidence=control_evidence,
        )
        business_actions = _collect_business_actions(events)

        # 9. notes + suggested_actions
        notes: list[str] = []
        suggested: list[str] = []
        # Unit 5: 检测是否需要 interrupt 请求控制日志
        interrupt_request = None
        if should_request_control_log(
            first_anomaly=first_anomaly,
            classification=classification_enum.value,
            has_control_log=has_control_log,
        ):
            interrupt_request = build_interrupt_request(
                reason=(
                    "板端状态流看似正常或证据不足以解释外部 FAIL; "
                    "请提供同次执行的控制脚本日志, 或选择不提供 (诚实降级)。"
                ),
            )
            notes.append("已生成控制脚本日志请求 (interrupt); CLI 应提示用户。")
            suggested.append("提供控制脚本日志路径以确认故障归因。")
        if first_anomaly is None and not has_control_log:
            notes.append("未发现板端异常; 外部 FAIL 不等于产品故障, 见 Plan R14。")
            suggested.append("提供同次执行的控制脚本日志以确认是否自动化误报。")
        if not is_complete:
            notes.append("板端证据不完整; 分类降级以避免过早结论。")
            suggested.append("检查是否有缺失的板端回调或异步事件。")
        if first_anomaly is not None and has_direct_evidence:
            notes.append(
                "板端与控制脚本均有失败信号; 请对照「控制脚本要点」与板端首异常判断主责。"
            )

        result: dict[str, Any] = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "run_label": label or "单次测试执行",
            "classification": classification_enum.value,
            "root_cause_confidence": root_cause_confidence,
            "scenario": scenario,
            "scenario_confidence": scenario_confidence,
            "business_actions": business_actions,
            "first_anomaly": first_anomaly,
            "evidence_refs": [
                {
                    "ref_id": r.ref_id,
                    "source": r.source,
                    "line_no": r.line_no,
                    "timestamp": r.timestamp,
                    "raw_text": r.raw_text,
                    "module": r.module,
                }
                for r in evidence_refs
            ],
            "timeline": timeline,
            "root_cause_chain": root_cause_chain,
            "control_log_used": has_control_log,
            "control_evidence": control_evidence,
            "external_result": "FAIL",
            "notes": notes,
            "suggested_actions": suggested,
            "_meta": {
                "dry_run": dry_run,
                "thread_id": thread_id,
                "control_log_path": control_log_path,
                "output_dir": output_dir,
                "events_count": len(events),
                "interrupt_request": interrupt_request,
                "control_log_events": len(control_events),
                "timeline_total_before_filter": len(events),
            },
        }
        return result


_NOISE_RAW_RE = re.compile(
    r"CPU USAGE|RingPlayOnce|no ring file|OFONO_DFX|^\s*~~~+\s*$",
    re.IGNORECASE,
)
_TS_PREFIX_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+)?"
    r"(?:\d{4}-\d{2}-\d{2}\s+\[[\d.]+\]\s*)?"
)


def _shorten_log_snippet(text: str, *, max_len: int = 160) -> str:
    """去掉行首时间戳壳, 截断过长摘要。"""
    cleaned = (text or "").strip()
    # 若含 Tab 分隔的 merge 行, 取板端侧
    if "\t" in cleaned:
        cleaned = cleaned.split("\t", 1)[-1].strip()
    cleaned = _TS_PREFIX_RE.sub("", cleaned).strip()
    # 去掉 modemcli> 前缀噪音但保留其后内容
    if "modemcli>" in cleaned:
        cleaned = cleaned.split("modemcli>", 1)[-1].strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _collect_business_actions(events: list[dict]) -> list[str]:
    """从 command 事件收集可读业务动作名。"""
    mapping = {
        "call": "Call",
        "sms": "SMS",
        "data_ping": "Data/Ping",
        "setting": "Setting",
    }
    seen: list[str] = []
    for ev in events:
        if ev.get("kind") != "command":
            continue
        label = mapping.get(ev.get("business_action") or "")
        if label and label not in seen:
            seen.append(label)
    return seen


def _control_evidence_items(control_events: list[dict]) -> list[dict[str, Any]]:
    """抽出控制日志中的直接证据行, 供报告「控制脚本要点」。"""
    items: list[dict[str, Any]] = []
    for ev in control_events:
        if not ev.get("has_direct_evidence"):
            continue
        raw = ev.get("raw_text") or ""
        items.append(
            {
                "line_no": ev.get("line_no"),
                "summary": _shorten_log_snippet(raw, max_len=200),
                "raw_text": raw,
            }
        )
    return items


def _is_significant_event(ev: dict) -> bool:
    """时间线只保留对工程师有用的事件。"""
    kind = ev.get("kind")
    raw = ev.get("raw_text") or ""
    if _NOISE_RAW_RE.search(raw):
        return False
    if kind == "command":
        return True
    if kind == "session_entry":
        return False
    if kind in ("callback", "response"):
        outcome = ev.get("terminal_outcome")
        if outcome == "failure":
            return True
        if outcome == "success":
            low = raw.lower()
            # ping 回显
            if "bytes from" in low:
                return True
            # 排除协议栈噪声 (IMS_/AT_/RIL 长日志里常含 SEND OK)
            if re.search(r"\b(IMS_|AT_|RIL|SIP_|OFONO)\b", raw):
                return False
            # 仅短业务回显
            payload = raw.split("\t", 1)[-1] if "\t" in raw else raw
            if len(payload) <= 120 and re.search(
                r"\b(OK|ping OK|ifconfig ok)\b",
                payload,
                re.IGNORECASE,
            ):
                return True
            return False
        return False
    return False


def _build_timeline(events: list[dict], refs: list) -> list[dict[str, Any]]:
    """从 events 构造**精简**时间线 (仅命令 + 明确成败回调; ping 回复合并)。"""
    timeline: list[dict[str, Any]] = []
    by_line: dict[int, object] = {r.line_no: r for r in refs if r.line_no}
    omitted = 0
    ping_burst: list[dict] = []

    def _flush_ping_burst() -> None:
        nonlocal ping_burst
        if not ping_burst:
            return
        first = ping_burst[0]
        n = len(ping_burst)
        if n == 1:
            timeline.append(first)
        else:
            timeline.append(
                {
                    "ts": first.get("ts"),
                    "event": f"ping 回复成功 ×{n}（已合并连续 icmp 回显）",
                    "ref_id": first.get("ref_id"),
                    "source_module": first.get("source_module"),
                    "kind": "ping_burst",
                }
            )
        ping_burst = []

    for ev in events:
        if ev.get("kind") not in ("command", "callback", "response", "session_entry"):
            continue
        if not _is_significant_event(ev):
            omitted += 1
            continue
        line_no = int(ev.get("line_no") or 0)
        ref = by_line.get(line_no)
        ref_id = getattr(ref, "ref_id", None) if ref else None
        desc = _timeline_description(ev)
        item = {
            "ts": ev.get("device_ts") or ev.get("capture_ts"),
            "event": desc,
            "ref_id": ref_id,
            "source_module": ev.get("module"),
            "kind": ev.get("kind"),
        }
        raw = (ev.get("raw_text") or "").lower()
        if ev.get("terminal_outcome") == "success" and "bytes from" in raw:
            ping_burst.append(item)
            continue
        _flush_ping_burst()
        timeline.append(item)

    _flush_ping_burst()
    if omitted:
        timeline.append(
            {
                "ts": None,
                "event": f"（已省略 {omitted} 条噪声/未知回调, 详见 analysis.json）",
                "ref_id": None,
                "source_module": None,
                "kind": "omitted_summary",
            }
        )
    return timeline


def _timeline_description(ev: dict) -> str:
    """生成时间线条目的一句话描述。"""
    kind = ev.get("kind")
    cmd = ev.get("command_name")
    args = ev.get("args") or []
    module = ev.get("module")
    outcome = ev.get("terminal_outcome")
    business = ev.get("business_action")

    if kind == "command":
        arg_str = " ".join(str(a) for a in args[:4])
        if len(args) > 4:
            arg_str += " …"
        biz = business or "unknown"
        mod = f"; 模块={module}" if module else ""
        return f"{cmd} {arg_str}".strip() + f"  [{biz}{mod}]"
    if kind in ("callback", "response"):
        snippet = _shorten_log_snippet(ev.get("raw_text") or "", max_len=80)
        label = "成功" if outcome == "success" else "失败" if outcome == "failure" else "回调"
        mod = module or "-"
        return f"{label} [{mod}] {snippet}".strip()
    return f"事件 ({kind})"


def _build_root_cause_chain(
    first_anomaly: dict | None,
    refs: list,
    *,
    control_evidence: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """构造最小根因链: trigger → propagation → terminal impact。"""
    if first_anomaly is None and not control_evidence:
        return []
    chain: list[dict[str, Any]] = []
    if first_anomaly is not None:
        chain.append(
            {
                "role": "trigger",
                "description": first_anomaly.get("summary") or "首个板端异常",
                "ref_ids": [first_anomaly["ref_id"]] if first_anomaly.get("ref_id") else [],
                "gap": None,
            }
        )
        chain.append(
            {
                "role": "propagation",
                "description": "异常影响后续业务观察或验收",
                "ref_ids": [],
                "gap": "传播路径未从日志自动还原; 请结合命令顺序人工确认",
            }
        )
    if control_evidence:
        ctrl = control_evidence[0]
        chain.append(
            {
                "role": "terminal_impact",
                "description": f"控制脚本判定失败: {ctrl.get('summary')}",
                "ref_ids": [],
                "gap": None,
            }
        )
    elif first_anomaly is not None:
        chain.append(
            {
                "role": "terminal_impact",
                "description": "外部 case 结果为 FAIL",
                "ref_ids": [],
                "gap": None,
            }
        )
    return chain


__all__ = ["AnalysisService"]
