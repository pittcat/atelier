"""ModemLogAnalyzer —— Agent Runner (U2)。

按 Plan §5 Unit 2:
  - 入口: ``run_agent_analyze(...)`` 返回 AnalysisResult dict。
  - 流程:
      1. deterministic preprocess (parse + evidence + control summary)
         → run_context.set(bundle)
      2. ``build_agent().invoke(messages, thread_id)`` 调用 Deep Agent
      3. 从最后一条 assistant 消息抽取 JSON, ``AnalysisResult.model_validate``
      4. 校验 evidence_refs ref_id 必须来自 preprocess (S5: 不得假 EV-NNNN)
      5. ``clear()`` 释放 run_context (无论成功/失败)
  - ``dry_run=True``: 跳过 invoke, 返回最小占位 dict, 不写文件 (S2)。
  - ``build_agent`` 通过 monkeypatch 在测试中替换; 真实路径从 ``agent.build_agent`` 拉。

约束 (硬规矩):
  - **不得** 在 agent 失败时自动 fallback 到 AnalysisService.run_analyze;
    失败必须显式抛错 (Plan S5)。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from modem_log_analyzer import run_context as rc
from modem_log_analyzer.contracts import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisResult,
    Classification,
)
from modem_log_analyzer.control_log_policy import (
    has_direct_automation_evidence,
    parse_control_log,
)
from modem_log_analyzer.evidence import build_evidence_index
from modem_log_analyzer.log_parser import parse_evb_log

logger = logging.getLogger(__name__)


# ============================================================
# 预处理: 与 AnalysisService 复用同一份 deterministic 逻辑
# ============================================================
def preprocess_evb_run(
    *,
    evb_log_path: str,
    control_log_path: str | None,
    label: str | None,
) -> dict[str, Any]:
    """对一次 analyze 做确定性预处理, 返回 bundle dict。

    Bundle 字段:
      - run_label, evb_log_path, control_log_path
      - command_summary: list[{ref_id, command, line_no}]
      - evidence_refs:   list[str] (EV-NNNN)
      - control_summary:  list[{line_no, summary}] | None
      - control_events_count: int
      - interrupt_request: dict | None (Plan R15: 何时需要控制日志)
    """
    p = Path(evb_log_path)
    raw_text = p.read_text(encoding="utf-8", errors="replace")
    events = parse_evb_log(raw_text)
    refs = build_evidence_index(events, source=p.name)
    by_line = {r.line_no: r for r in refs}

    command_summary: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("kind") != "command":
            continue
        ln = int(ev.get("line_no") or 0)
        ref = by_line.get(ln)
        if ref is None:
            continue
        command_summary.append(
            {
                "ref_id": ref.ref_id,
                "command": (ev.get("command_name") or ""),
                "line_no": ln,
                "module": ev.get("module"),
            }
        )

    control_summary: list[dict[str, Any]] | None = None
    control_events: list[dict] = []
    if control_log_path:
        cp = Path(control_log_path)
        if cp.exists() and cp.is_file():
            try:
                ctext = cp.read_text(encoding="utf-8", errors="replace")
                control_events = parse_control_log(ctext)
                control_summary = [
                    {
                        "line_no": ev.get("line_no"),
                        "summary": (ev.get("raw_text") or "").strip()[:200],
                        "has_direct_evidence": ev.get("has_direct_evidence", False),
                    }
                    for ev in control_events
                    if ev.get("has_direct_evidence")
                ]
            except Exception:  # 读取失败不应让 preprocess 整体失败
                control_summary = None
                control_events = []

    # interrupt 决策 (Plan R15): 板端无异常 + 没控制日志 → 请求
    interrupt_request = None
    has_anomaly = any(
        (ev.get("terminal_outcome") == "failure")
        or (ev.get("kind") == "callback")
        and ("ERROR" in (ev.get("raw_text") or "").upper())
        for ev in events
    )
    has_control_log = control_log_path is not None
    has_control_evidence = bool(control_events) and has_direct_automation_evidence(control_events)
    if not has_anomaly and not has_control_log:
        interrupt_request = {
            "type": "REQUEST_CONTROL_LOG",
            "why": "板端未发现明显异常; 外部 FAIL 可能源自控制脚本; 建议提供同次执行的控制日志。",
            "options": {
                "approve": "提供控制脚本日志路径",
                "reject": "不提供 (诚实降级)",
            },
        }

    return {
        "run_label": label or "单次测试执行",
        "evb_log_path": str(p),
        "control_log_path": str(control_log_path) if control_log_path else None,
        "command_summary": command_summary,
        "evidence_refs": [r.ref_id for r in refs],
        "control_summary": control_summary,
        "control_events_count": len(control_events),
        "has_control_evidence": has_control_evidence,
        "has_control_log": has_control_log,
        "interrupt_request": interrupt_request,
    }


# ============================================================
# 校验: 草稿 ref_id 必须出现在 preprocess bundle
# ============================================================
def _validate_refs_against_bundle(draft: dict, bundle: dict) -> None:
    """校验草稿里出现的 EV-NNNN 都来自 preprocess bundle (Plan S5)。

    仅在 ``bundle['evidence_refs']`` 非空时执行; 否则不阻塞 (允许 AI 在证据
    极简场景下给出空列表)。
    """
    valid_refs = set(bundle.get("evidence_refs") or [])
    if not valid_refs:
        return
    refs_in_draft: set[str] = set()
    for r in draft.get("evidence_refs") or []:
        rid = r.get("ref_id") if isinstance(r, dict) else None
        if rid:
            refs_in_draft.add(rid)
    fa = draft.get("first_anomaly") or {}
    if isinstance(fa, dict) and fa.get("ref_id"):
        refs_in_draft.add(fa["ref_id"])
    for link in draft.get("root_cause_chain") or []:
        for rid in link.get("ref_ids") or []:
            if isinstance(rid, str):
                refs_in_draft.add(rid)
    fake = refs_in_draft - valid_refs
    if fake:
        raise ValueError(
            f"INVALID: draft references unknown EV-NNNN not in preprocess bundle: "
            f"{sorted(fake)}; valid: {sorted(valid_refs)[:10]}{'...' if len(valid_refs) > 10 else ''}"
        )


# ============================================================
# 解析: 从消息中提取 AnalysisResult JSON
# ============================================================
def _extract_draft_from_messages(messages: list) -> dict | None:
    """从 messages 中提取最后一条 assistant 消息里的 AnalysisResult JSON。

    支持两种形态:
      1. content 是 str 且包含 JSON 代码块 (```json ... ```) 或裸 JSON。
      2. content 是 list, 逐项 text 内含 JSON。
    找不到合法 JSON → 返回 None (caller 决定报错)。
    """
    import re

    if not messages:
        return None
    last = messages[-1]
    # dict 形态
    if isinstance(last, dict):
        content = last.get("content")
    else:
        content = getattr(last, "content", None)

    candidates: list[str] = []
    if isinstance(content, str):
        candidates.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content")
                if isinstance(txt, str):
                    candidates.append(txt)
            elif isinstance(item, str):
                candidates.append(item)

    for txt in candidates:
        # 优先匹配 ```json ... ``` 代码块
        m = re.search(r"```json\s*(\{.*?\})\s*```", txt, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        # 否则尝试提取首段 { ... }
        m2 = re.search(r"(\{[\s\S]*\})", txt)
        if m2:
            try:
                return json.loads(m2.group(1))
            except Exception:
                continue
    return None


# ============================================================
# build_agent 注入点 (测试可 monkeypatch)
# ============================================================
def build_agent():  # pragma: no cover - 默认 delegate
    """Lazy import build_agent, allow test monkeypatch."""
    from modem_log_analyzer.agent import build_agent as _ba

    return _ba()


# ============================================================
# 主入口
# ============================================================
def run_agent_analyze(
    *,
    evb_log_path: str,
    output_dir: str,
    control_log_path: str | None = None,
    label: str | None = None,
    thread_id: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Agent 主路径: preprocess → invoke → schema 校验。

    Returns:
        AnalysisResult dict (符合 contracts.AnalysisResult schema)。

    Raises:
        ValueError: 草稿缺字段 / 引用假 EV-NNNN。
        RuntimeError: agent.invoke 抛错; 透传原始 message。
    """
    bundle = preprocess_evb_run(
        evb_log_path=evb_log_path,
        control_log_path=control_log_path,
        label=label,
    )
    rc.set(bundle)
    try:
        if dry_run:
            # dry-run: 不调 LLM, 返回占位 dict (诚实标记)
            return _dry_run_placeholder(bundle, output_dir=output_dir, thread_id=thread_id)

        agent = build_agent()
        config: dict[str, Any] = {}
        # Checkpointer 强制要 thread_id (Plan U6 真实样本跑通): 缺省自动生成
        effective_thread_id = thread_id or f"modem-la-{uuid.uuid4().hex}"
        config["configurable"] = {"thread_id": effective_thread_id}

        try:
            from langchain_core.messages import HumanMessage
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "langchain_core not installed; required for agent_runner.run_agent_analyze"
            ) from e

        human_msg = _compose_human_message(bundle)
        try:
            invoke_input: dict[str, Any] = {"messages": [HumanMessage(content=human_msg)]}
            result = agent.invoke(invoke_input, config=config or None)
        except Exception as e:
            logger.exception("agent.invoke failed")
            raise RuntimeError(f"agent invoke failed: {e}") from e

        messages = (result or {}).get("messages") if isinstance(result, dict) else None
        draft = _extract_draft_from_messages(list(messages or []))
        if draft is None:
            raise ValueError(
                "INVALID: agent did not return a JSON AnalysisResult draft in last message"
            )

        # 用 contracts 强制校验 schema
        try:
            AnalysisResult.model_validate(draft)
        except Exception as e:
            raise ValueError(f"INVALID: draft schema check failed: {e}") from e

        # 二次校验: ref_id 真伪
        _validate_refs_against_bundle(draft, bundle)

        # 注入 _meta (与 AnalysisService 一致, 让 renderer/Gateway 无差异)
        draft["_meta"] = {
            "dry_run": False,
            "thread_id": thread_id,
            "control_log_path": bundle.get("control_log_path"),
            "output_dir": output_dir,
            "events_count": len(bundle.get("command_summary", [])),
            "interrupt_request": bundle.get("interrupt_request"),
            "control_log_events": bundle.get("control_events_count", 0),
            "runner": "agent_runner",
        }
        return draft
    finally:
        rc.clear()


def _compose_human_message(bundle: dict) -> str:
    """组装一次性 HumanMessage, 给 Agent 足够上下文 + 期望输出 schema。"""
    parts = [
        "请基于本 run 的预处理证据分析这次 NuttX EVB 失败日志。",
        "",
        "## Run 元信息",
        f"- run_label: {bundle.get('run_label')}",
        f"- evb_log_path: {bundle.get('evb_log_path')}",
        f"- control_log_path: {bundle.get('control_log_path') or '(未提供)'}",
        "",
        "## 工作流程",
        "1. 调用 `get_preprocessed_bundle` 读取命令摘要与 evidence_refs (EV-NNNN)。",
        "2. 需要更细原文时调用 `read_evb_log_slice(start_line, end_line)`。",
        "3. 若提供了控制脚本日志, 可调用 `read_control_log` 读取要点。",
        "4. 推断场景 / 首异常 / 根因链, 形成 AnalysisResult 草稿。",
        "5. 调用 `validate_analysis_draft` 校验草稿; 不合法则回到第 4 步修正。",
        "6. **最终回复只发一段 JSON** (可包在 ```json ... ```), 不要附加解释。",
        "",
        "## 关键约束",
        "- 所有 evidence_ref 必须引用真实 EV-NNNN (来自 bundle.evidence_refs)。",
        "- 分类必须是 6 枚举之一 (见 contracts.Classification)。",
        "- 不得直接 write_file / bash / git_push; 产物落盘由 CLI 负责。",
    ]
    return "\n".join(parts)


def _dry_run_placeholder(bundle: dict, *, output_dir: str, thread_id: str | None) -> dict[str, Any]:
    """dry-run 占位: 不调 LLM, 返回诚实降级 dict。"""
    classification = Classification.DEVICE_EVIDENCE_INCOMPLETE
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "run_label": bundle.get("run_label", "单次测试执行"),
        "classification": classification.value,
        "root_cause_confidence": "low",
        "scenario": None,
        "scenario_confidence": None,
        "first_anomaly": None,
        "evidence_refs": [],
        "timeline": [],
        "root_cause_chain": [],
        "control_log_used": bundle.get("has_control_log", False),
        "external_result": "FAIL",
        "notes": [
            "dry-run: 未调用 LLM, 不写产物。",
            f"预处理发现 {len(bundle.get('command_summary', []))} 个命令事件; "
            f"evidence_refs 数量 {len(bundle.get('evidence_refs', []))}。",
        ],
        "suggested_actions": ["去掉 --dry-run 真实调用 Agent 诊断。"],
        "_meta": {
            "dry_run": True,
            "thread_id": thread_id,
            "control_log_path": bundle.get("control_log_path"),
            "output_dir": output_dir,
            "events_count": len(bundle.get("command_summary", [])),
            "interrupt_request": bundle.get("interrupt_request"),
            "control_log_events": bundle.get("control_events_count", 0),
            "runner": "agent_runner.dry_run",
        },
    }


__all__ = [
    "preprocess_evb_run",
    "run_agent_analyze",
    "build_agent",
]