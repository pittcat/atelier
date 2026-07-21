"""U2: agent_runner 契约 (Fake graph 集成)。

按 Plan Unit 2:
  - ``run_agent_analyze`` 必须**真实地** set run_context 后 invoke 一个图,
    从最终消息中提取 AnalysisResult JSON, 经 schema 硬校验, 落库前 dump。
  - 失败语义:
      * 草稿字段缺失/类型错 → 拒绝 (有界重试 + 显式错误, 不得静默回退到规则服务)。
      * LLM invoke 抛错 → 显式错误。
      * 验证始终拒绝"假 EV-NNNN" (ref 不在 preprocess 里)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# Test fixtures
# ============================================================
def _write_evb(tmp_path: Path) -> Path:
    log = tmp_path / "merge.log"
    log.write_text(
        "\n".join(
            [
                "[2026-07-21 10:00:00.000][ap] >>> modemcli debug_bes_rpc 0 13800001234",
                "[2026-07-21 10:00:01.000][ap] Call established",
                "[2026-07-21 10:00:30.000][ap] ERROR no response from network",
                "[2026-07-21 10:00:31.000][ap] case_result=FAIL",
            ]
        ),
        encoding="utf-8",
    )
    return log


def _build_fake_graph(replies: list[dict]):
    """构造一个 Fake LangGraph 图, invoke 时按顺序返回 ``replies`` 中的消息。"""
    from langgraph.graph import START, StateGraph
    from typing_extensions import TypedDict

    class _S(TypedDict, total=False):
        messages: list

    index = {"i": 0}

    def _node(state: dict) -> dict:
        msgs = list(state.get("messages") or [])
        i = index["i"]
        if i < len(replies):
            msgs.append(replies[i])
            index["i"] = i + 1
        return {"messages": msgs}

    g = StateGraph(_S)
    g.add_node("echo", _node)
    g.add_edge(START, "echo")
    return g.compile()


# ============================================================
# 测试: monkeypatch build_agent + invoke, Fake graph 返回合法草稿
# ============================================================
def test_runner_uses_agent_invoke(monkeypatch, tmp_path):
    """runner 必须 set run_context + invoke agent; 不是直接走 AnalysisService。"""
    from modem_log_analyzer import agent_runner, run_context as rc
    from modem_log_analyzer import contracts

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # 真实 preprocess 后, agent 会通过工具读到 1 个 evidence_ref, ref_id = EV-0001
    # 草稿里必须引用 EV-NNNN
    draft = {
        "schema_version": contracts.ANALYSIS_SCHEMA_VERSION,
        "run_label": "loop75",
        "classification": contracts.Classification.DEVICE_FAILURE_CONFIRMED.value,
        "root_cause_confidence": "medium",
        "scenario": "语音通话 (Call)",
        "scenario_confidence": "high",
        "first_anomaly": None,
        "evidence_refs": [
            {
                "ref_id": "EV-0001",
                "source": "merge.log",
                "line_no": 3,
                "timestamp": "2026-07-21 10:00:30.000",
                "raw_text": "[2026-07-21 10:00:30.000][ap] ERROR no response from network",
                "module": "ap",
            }
        ],
        "timeline": [],
        "root_cause_chain": [],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": [],
        "suggested_actions": [],
    }

    fake = _build_fake_graph([{"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)}])

    # Patch build_agent so we don't need real LLM
    monkeypatch.setattr(agent_runner, "build_agent", lambda: fake)
    # Make sure no leftover context
    rc.clear()
    try:
        result = agent_runner.run_agent_analyze(
            evb_log_path=str(evb),
            output_dir=str(out_dir),
            control_log_path=None,
            label="loop75",
            thread_id=None,
            overwrite=False,
            dry_run=False,
        )
    finally:
        rc.clear()

    assert isinstance(result, dict)
    assert result["classification"] == "DEVICE_FAILURE_CONFIRMED"
    assert result["run_label"] == "loop75"
    assert result["evidence_refs"][0]["ref_id"] == "EV-0001"


def test_runner_rejects_invalid_draft(monkeypatch, tmp_path):
    """LLM 返回的草稿若缺字段, runner 必须拒绝 (非静默回退)。"""
    from modem_log_analyzer import agent_runner, run_context as rc

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    bad_draft = {"schema_version": "0.1.0", "run_label": "x"}  # 缺 classification
    fake = _build_fake_graph([{"role": "assistant", "content": json.dumps(bad_draft)}])
    monkeypatch.setattr(agent_runner, "build_agent", lambda: fake)
    rc.clear()

    try:
        import pytest

        with pytest.raises(ValueError) as ei:
            agent_runner.run_agent_analyze(
                evb_log_path=str(evb),
                output_dir=str(out_dir),
                control_log_path=None,
                label="x",
                thread_id=None,
                overwrite=False,
                dry_run=False,
            )
        assert "INVALID" in str(ei.value).upper() or "schema" in str(ei.value).lower()
    finally:
        rc.clear()


def test_runner_rejects_fake_evidence_ref(monkeypatch, tmp_path):
    """Agent 草稿里出现 preprocess 没有的 EV-NNNN → 拒绝。"""
    from modem_log_analyzer import agent_runner, run_context as rc
    from modem_log_analyzer import contracts

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # 真实 preprocess 只会产出 EV-0001; 草稿造假 EV-9999 应被拒
    bad_draft = {
        "schema_version": contracts.ANALYSIS_SCHEMA_VERSION,
        "run_label": "x",
        "classification": contracts.Classification.DEVICE_FAILURE_CONFIRMED.value,
        "root_cause_confidence": "low",
        "evidence_refs": [
            {
                "ref_id": "EV-9999",
                "source": "merge.log",
                "line_no": 99,
                "timestamp": None,
                "raw_text": "fabricated",
                "module": "ap",
            }
        ],
        "timeline": [],
        "root_cause_chain": [],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": [],
        "suggested_actions": [],
    }
    fake = _build_fake_graph([{"role": "assistant", "content": json.dumps(bad_draft)}])
    monkeypatch.setattr(agent_runner, "build_agent", lambda: fake)
    rc.clear()

    try:
        import pytest

        with pytest.raises(ValueError):
            agent_runner.run_agent_analyze(
                evb_log_path=str(evb),
                output_dir=str(out_dir),
                control_log_path=None,
                label="x",
                thread_id=None,
                overwrite=False,
                dry_run=False,
            )
    finally:
        rc.clear()


def test_runner_surfaces_invoke_error(monkeypatch, tmp_path):
    """agent.invoke 抛错 → runner 抛错 (不静默)。"""
    from modem_log_analyzer import agent_runner, run_context as rc

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    class _Boom:
        def invoke(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(agent_runner, "build_agent", lambda: _Boom())
    rc.clear()

    try:
        import pytest

        with pytest.raises(RuntimeError, match="network down"):
            agent_runner.run_agent_analyze(
                evb_log_path=str(evb),
                output_dir=str(out_dir),
                control_log_path=None,
                label="x",
                thread_id=None,
                overwrite=False,
                dry_run=False,
            )
    finally:
        rc.clear()


def test_runner_dry_run_does_not_invoke(monkeypatch, tmp_path):
    """dry_run=True: 不调 LLM, 不写产物, 但能拿到 preprocess 摘要。"""
    from modem_log_analyzer import agent_runner, run_context as rc

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    called = {"flag": False}

    def _explode():
        called["flag"] = True
        raise AssertionError("build_agent must not be called in dry-run")

    monkeypatch.setattr(agent_runner, "build_agent", _explode)
    rc.clear()

    try:
        result = agent_runner.run_agent_analyze(
            evb_log_path=str(evb),
            output_dir=str(out_dir),
            control_log_path=None,
            label="x",
            thread_id=None,
            overwrite=False,
            dry_run=True,
        )
    finally:
        rc.clear()

    assert called["flag"] is False
    assert result["classification"] == "DEVICE_EVIDENCE_INCOMPLETE" or result["classification"]
    assert result["_meta"]["dry_run"] is True
    # dry-run 不能写文件
    assert not (out_dir / "report.md").exists()
    assert not (out_dir / "analysis.json").exists()

# ============================================================
# 草稿规范化 (缺口修复)
# ============================================================
def test_normalize_messy_agent_draft_fills_report_fields(tmp_path):
    """真实 LLM 常见坏草稿 → 规范化后报告字段齐全。"""
    from modem_log_analyzer import agent_runner

    evb = _write_evb(tmp_path)
    ctrl = tmp_path / "control.log"
    ctrl.write_text(
        "2026-07-21 10:00:40 ERROR check ping addr: map.baidu.com state: 1 fail\n",
        encoding="utf-8",
    )
    bundle = agent_runner.preprocess_evb_run(
        evb_log_path=str(evb),
        control_log_path=str(ctrl),
        label="loop75",
    )
    assert bundle["has_control_log"] is True
    assert bundle["has_control_evidence"] is True
    assert bundle.get("scenario")

    # 取一个真实 EV
    rid = bundle["evidence_refs"][0]
    known = next(x for x in bundle["evidence_index"] if x["ref_id"] == rid)

    messy = {
        "schema_version": "1.0.0",
        "classification": "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "evidence_refs": [
            {"ref_id": rid, "source": "merge.log", "raw_text": known["raw_text"]}
        ],
        "first_anomaly": {
            "evidence_ref": {"ref_id": rid, "source": "merge.log", "raw_text": "nested"},
            "note": "首包超时触发控制脚本判 fail",
        },
        "root_cause_chain": [
            {
                "role": "trigger",
                "description": f"启动 ping 后异常 ({rid})",
            }
        ],
        "notes": ["demo"],
    }
    out = agent_runner.normalize_agent_draft(messy, bundle)
    assert out["schema_version"] == "0.1.0"
    assert out["scenario"] == bundle["scenario"]
    assert out["control_log_used"] is True
    fa = out["first_anomaly"]
    assert fa["ref_id"] == rid
    assert fa["line_no"] == known["line_no"]
    assert "首包超时" in fa["summary"]
    assert rid in out["root_cause_chain"][0]["ref_ids"]
    assert out["evidence_refs"][0].get("line_no") == known["line_no"]


def test_runner_normalizes_and_persists_meta(monkeypatch, tmp_path):
    """invoke 后规范化 + atomic_write 保留 _meta.runner。"""
    from modem_log_analyzer import agent_runner, run_context as rc
    from modem_log_analyzer.report import atomic_write_artifacts

    evb = _write_evb(tmp_path)
    ctrl = tmp_path / "control.log"
    ctrl.write_text(
        "2026-07-21 ERROR check ping addr: x state: 1 fail\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # 先 preprocess 拿真实 ref
    bundle = agent_runner.preprocess_evb_run(
        evb_log_path=str(evb), control_log_path=str(ctrl), label="x"
    )
    rid = bundle["evidence_refs"][0]
    known = next(x for x in bundle["evidence_index"] if x["ref_id"] == rid)

    draft = {
        "schema_version": "1.0.0",
        "classification": "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "evidence_refs": [
            {"ref_id": rid, "source": "merge.log", "raw_text": known["raw_text"]}
        ],
        "first_anomaly": {
            "evidence_ref": {"ref_id": rid, "raw_text": "x"},
            "note": "timeout",
        },
        "root_cause_chain": [],
        "notes": [],
    }
    fake = _build_fake_graph(
        [{"role": "assistant", "content": json.dumps(draft, ensure_ascii=False)}]
    )
    monkeypatch.setattr(agent_runner, "build_agent", lambda: fake)
    rc.clear()
    try:
        result = agent_runner.run_agent_analyze(
            evb_log_path=str(evb),
            output_dir=str(out_dir),
            control_log_path=str(ctrl),
            label="x",
            thread_id="t-1",
            overwrite=True,
            dry_run=False,
        )
    finally:
        rc.clear()

    assert result["_meta"]["runner"] == "agent_runner"
    assert result["control_log_used"] is True
    assert result["first_anomaly"]["ref_id"] == rid
    assert result["first_anomaly"]["line_no"] is not None
    assert result.get("scenario")
    assert result.get("control_evidence")

    atomic_write_artifacts(result=result, output_dir=str(out_dir), overwrite=True)
    saved = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert saved["_meta"]["runner"] == "agent_runner"
    assert saved["control_log_used"] is True
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "是否使用控制脚本日志**: 是" in md or "是否使用控制脚本日志**: `是`" in md or "**是否使用控制脚本日志**: 是" in md
    assert "行 None" not in md


def test_runner_rejects_automation_without_control_evidence(monkeypatch, tmp_path):
    from modem_log_analyzer import agent_runner, run_context as rc
    import pytest

    evb = _write_evb(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    bundle = agent_runner.preprocess_evb_run(
        evb_log_path=str(evb), control_log_path=None, label="x"
    )
    rid = bundle["evidence_refs"][0]
    known = next(x for x in bundle["evidence_index"] if x["ref_id"] == rid)
    draft = {
        "schema_version": "0.1.0",
        "classification": "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "evidence_refs": [
            {
                "ref_id": rid,
                "source": "merge.log",
                "line_no": known["line_no"],
                "raw_text": known["raw_text"],
                "module": None,
                "timestamp": None,
            }
        ],
        "timeline": [],
        "root_cause_chain": [],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": [],
        "suggested_actions": [],
    }
    fake = _build_fake_graph([{"role": "assistant", "content": json.dumps(draft)}])
    monkeypatch.setattr(agent_runner, "build_agent", lambda: fake)
    rc.clear()
    try:
        with pytest.raises(ValueError, match="TEST_AUTOMATION"):
            agent_runner.run_agent_analyze(
                evb_log_path=str(evb),
                output_dir=str(out_dir),
                control_log_path=None,
                label="x",
                thread_id=None,
                overwrite=False,
                dry_run=False,
            )
    finally:
        rc.clear()
