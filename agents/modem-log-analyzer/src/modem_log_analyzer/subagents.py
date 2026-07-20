"""ModemLogAnalyzer 的子代理清单。

按 AGENTS.md 规则:
  - 深度 ≤ 2 (main → sub,禁止 sub-sub)
  - 单一职责
  - 不互相调用

Unit 1 仅注册一个 subagent (``diagnostician``);
模板默认的 researcher / tester / reviewer 三件套不适合只读分析 Agent,被显式忽略。

Plan §5 U5 模型对齐:
  - 主代理 / subagent 模型走 env ``ATELIER_DEFAULT_MODEL`` /
    ``ATELIER_SUBAGENT_MODEL``,与 code-writer / compound-builder 对齐。
  - 缺省值与 ``llm.resolve_default_model`` 同源 (claude-opus-4-8 / claude-haiku-4-5)。
"""

from __future__ import annotations

import os

from modem_log_analyzer.prompts import SUBAGENT_PROMPTS


def _diagnostician_tools():
    """Diagnostician 工具: 仅项目级只读 + schema 校验。

    与 tools.build_tools() 一致,因为这是它能用的全部接口。
    """
    from modem_log_analyzer.tools import build_tools

    return build_tools()


def _make(name: str, description: str, prompt: str, tools: list, model_name: str) -> dict:
    from modem_log_analyzer.llm import get_llm

    return {
        "name": name,
        "description": description,
        "system_prompt": prompt,
        "tools": tools,
        "model": get_llm(model_name),
    }


def _resolve_subagent_model() -> str:
    """解析 subagent 默认模型。

    优先级:
      1. ``ATELIER_SUBAGENT_MODEL`` (显式覆盖)
      2. ``ATELIER_DEFAULT_MODEL`` (与主代理一致, 适合回放/对比)
      3. ``ANTHROPIC_MODEL``
      4. 缺省 ``claude-haiku-4-5-20251001`` (轻量 subagent)
    """
    return (
        os.getenv("ATELIER_SUBAGENT_MODEL")
        or os.getenv("ATELIER_DEFAULT_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "claude-haiku-4-5-20251001"
    )


SUBAGENTS: list[dict] = [
    _make(
        name="diagnostician",
        description=(
            "Synthesizes a single-pass diagnosis for a NuttX EVB failure log. "
            "Use AFTER preprocess_evb_run() has produced command_summary + "
            "evidence_refs (EV-NNNN). Returns an AnalysisResult draft that "
            "must reference only EV-NNNN from get_preprocessed_bundle; "
            "never writes files, never runs shell, never invents EV ids."
        ),
        prompt=SUBAGENT_PROMPTS["diagnostician"],
        tools=_diagnostician_tools(),
        model_name=_resolve_subagent_model(),
    ),
]


__all__ = ["SUBAGENTS", "_resolve_subagent_model"]
