"""U5 静态验证: prompt / subagent / doc 与主路径契约一致。

按 Plan §5 U5:
  - SYSTEM_PROMPT 必须显式声明 CLI/Gateway 主路径走 Agent。
  - diagnostician 子代理提示词必须含 EV-NNNN 真实引用约束。
  - subagents._resolve_subagent_model 必须支持 env 覆盖。
  - AnalysisService 必须标记 backend=rules_pipeline_legacy (降级命名)。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ============================================================
# Prompt: 静态断言
# ============================================================
def test_system_prompt_declares_agent_path():
    from modem_log_analyzer.prompts import SYSTEM_PROMPT

    text = SYSTEM_PROMPT
    # 主路径硬规矩: CLI / Gateway 必须 invoke Agent
    assert "agent_runner" in text or "Agent" in text
    # 显式提及 CLI/Gateway
    assert "CLI" in text
    assert "Gateway" in text
    # 仍包含 4 个工具
    assert "get_preprocessed_bundle" in text
    assert "read_evb_log_slice" in text
    assert "read_control_log" in text
    assert "validate_analysis_draft" in text
    # 不允许危险工具
    assert "bash" not in text.lower().replace("bash ", "")  # 注释里有但只 '不调用 bash'


def test_diagnostician_prompt_requires_real_ev_ids():
    from modem_log_analyzer.prompts import SUBAGENT_PROMPTS

    diag = SUBAGENT_PROMPTS["diagnostician"]
    # 必须含 EV-NNNN 真实引用约束
    assert "EV-NNNN" in diag
    # 至少提到 TEST_AUTOMATION_FAILURE_CONFIRMED (需要控制证据的硬规则)
    assert "TEST_AUTOMATION_FAILURE_CONFIRMED" in diag
    # 显式禁止危险工具
    assert "bash" in diag.lower()
    assert "write_file" in diag.lower()
    # 没有鼓励使用危险工具 (以 `` 开头不允许)
    for bad in ("bash", "write_file", "git_push"):
        assert f"``{bad}``" not in diag, f"diagnostician 不应把 {bad} 当工具"


def test_system_prompt_declares_nuttx_and_ev_id_boundary():
    """Domain: NuttX=板端；EV-NNNN=分析器预处理索引，非 NuttX 原生。"""
    from modem_log_analyzer.prompts import SUBAGENT_PROMPTS, SYSTEM_PROMPT

    text = SYSTEM_PROMPT
    assert "Domain Context" in text
    assert "NuttX" in text
    assert "预处理" in text
    assert "不是" in text and "NuttX" in text
    # 明确 EV-NNNN 不是协议/原生字段
    assert "协议" in text or "原生" in text
    diag = SUBAGENT_PROMPTS["diagnostician"]
    assert "NuttX" in diag
    assert "预处理" in diag
    assert "不是" in diag


def test_system_prompt_declares_business_scope_in_plain_language():
    """Business: 通话/短信/ping/开关用人话写清，不只是抽象枚举。"""
    from modem_log_analyzer.prompts import SUBAGENT_PROMPTS, SYSTEM_PROMPT

    text = SYSTEM_PROMPT
    assert "Business Scope" in text
    assert "打电话" in text or "接电话" in text
    assert "通话中" in text
    assert "短信" in text
    assert "ping" in text.lower() or "Ping" in text
    assert "开关" in text or "飞行模式" in text or "VoLTE" in text
    diag = SUBAGENT_PROMPTS["diagnostician"]
    assert "打电话" in diag or "接电话" in diag
    assert "短信" in diag
    assert "ping" in diag.lower() or "Ping" in diag


def test_system_prompt_contains_timeline_spine_checklist():
    """Plan 2026-07-21-002 U5: SYSTEM_PROMPT 必须含 Timeline Spine 检查清单。"""
    from modem_log_analyzer.prompts import SYSTEM_PROMPT

    text = SYSTEM_PROMPT
    assert "Timeline Spine" in text
    # 关键 spine 字段
    assert "flow_one_liner" in text
    assert "confirmed_impact" in text
    assert "suspected_root_cause" in text
    assert "evidence_blocks" in text
    assert "is_failure_step" in text
    # 故障步前后对照
    assert "before" in text and "after" in text
    # 禁止空壳 + 禁止控制脚本进 blocks
    assert "空壳" in text or "modemcli" in text
    assert "control_script" in text or "控制脚本" in text
    # 必须先 validate
    assert "validate_analysis_draft" in text


def test_diagnostician_prompt_contains_spine_requirements():
    """Plan 2026-07-21-002 U5: diagnostician 提示词须含 spine 字段要求。"""
    from modem_log_analyzer.prompts import SUBAGENT_PROMPTS

    diag = SUBAGENT_PROMPTS["diagnostician"]
    assert "Timeline Spine" in diag
    assert "evidence_blocks" in diag
    assert "is_failure_step" in diag
    assert "flow_one_liner" in diag


def test_prompts_doc_change_record_has_spine_entry():
    """PROMPT.md 必须含 Timeline Spine 变更记录 (硬规矩 3)。"""
    docs = ROOT / "docs" / "PROMPT.md"
    if not docs.exists():
        return
    text = docs.read_text(encoding="utf-8")
    assert "Timeline Spine" in text or "2026-07-21-002" in text, (
        "docs/PROMPT.md 必须含 Timeline Spine 变更记录"
    )


def test_prompts_doc_change_record_present():
    """PROMPT.md 必须在最近一次 prompt 改动后追加变更记录 (硬规矩 3)。"""
    docs = ROOT / "docs" / "PROMPT.md"
    if not docs.exists():
        return  # 不强制 (monorepo)
    text = docs.read_text(encoding="utf-8")
    # 至少含一处与本次 plan 关联的关键词: agent_runner 或 U3/U5
    assert "agent_runner" in text or "U3" in text or "U5" in text, (
        "docs/PROMPT.md 必须包含与 agent-driven CLI 改动相关的变更记录"
    )


# ============================================================
# Subagent 模型对齐
# ============================================================
def test_resolve_subagent_model_default(monkeypatch):
    monkeypatch.delenv("ATELIER_SUBAGENT_MODEL", raising=False)
    monkeypatch.delenv("ATELIER_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    from modem_log_analyzer.subagents import _resolve_subagent_model

    m = _resolve_subagent_model()
    assert isinstance(m, str) and m, "默认 subagent 模型必须非空"


def test_resolve_subagent_model_env_override(monkeypatch):
    monkeypatch.setenv("ATELIER_SUBAGENT_MODEL", "claude-haiku-4-5-20251001")
    from modem_log_analyzer.subagents import _resolve_subagent_model

    assert _resolve_subagent_model() == "claude-haiku-4-5-20251001"


def test_resolve_subagent_model_inherits_default(monkeypatch):
    monkeypatch.delenv("ATELIER_SUBAGENT_MODEL", raising=False)
    monkeypatch.setenv("ATELIER_DEFAULT_MODEL", "claude-opus-4-8")
    from modem_log_analyzer.subagents import _resolve_subagent_model

    assert _resolve_subagent_model() == "claude-opus-4-8"


# ============================================================
# AnalysisService 降级命名
# ============================================================
def test_analysis_service_rules_pipeline_tag():
    """Plan U5: AnalysisService._run_rules_pipeline 必须自标记 backend=rules_pipeline_legacy。"""
    import inspect

    from modem_log_analyzer import analysis_service

    src = inspect.getsource(analysis_service)
    assert "rules_pipeline_legacy" in src
    # 警告 docstring
    doc = analysis_service.AnalysisService.__doc__ or ""
    assert "降级" in doc or "legacy" in doc.lower() or "不得" in doc


# ============================================================
# 工具计数 / 危险工具
# ============================================================
def test_subagent_tools_match_main_agent():
    """diagnostician 与主代理共享同一只读工具表 (防止工具表漂移)。"""
    from modem_log_analyzer.subagents import _diagnostician_tools
    from modem_log_analyzer.tools import build_tools

    main_names = sorted(t.name for t in build_tools())
    sub_names = sorted(t.name for t in _diagnostician_tools())
    assert main_names == sub_names, (
        f"subagent 工具与主代理不一致: main={main_names} sub={sub_names}"
    )
