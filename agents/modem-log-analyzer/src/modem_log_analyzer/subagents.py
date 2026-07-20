"""ModemLogAnalyzer 的子代理清单。

按 AGENTS.md 规则:
  - 深度 ≤ 2 (main → sub,禁止 sub-sub)
  - 单一职责
  - 不互相调用

Unit 1 仅注册一个 subagent (``diagnostician``);
模板默认的 researcher / tester / reviewer 三件套不适合只读分析 Agent,被显式忽略。
"""

from __future__ import annotations

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


SUBAGENTS: list[dict] = [
    _make(
        name="diagnostician",
        description=(
            "Synthesizes a single-pass diagnosis for a NuttX EVB failure log. "
            "Use AFTER Unit 3 has produced structured events + evidence index. "
            "Returns an AnalysisResult draft; never writes files or runs shell."
        ),
        prompt=SUBAGENT_PROMPTS["diagnostician"],
        tools=_diagnostician_tools(),
        model_name="claude-haiku-4-5-20251001",
    ),
]


__all__ = ["SUBAGENTS"]
