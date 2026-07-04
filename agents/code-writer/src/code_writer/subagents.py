"""Code Writer Agent 的子代理清单。

按 AGENTS.md 规则：
  - 深度 ≤ 2
  - 单一职责
  - 互相不调用
"""

from __future__ import annotations

from code_writer.tools import (
    search_docs_tool,
    search_codebase_tool,
    write_file_tool,
    read_file_tool,
    run_tests_tool,
    lint_tool,
)
from code_writer.llm import get_llm
from code_writer.prompts import SUBAGENT_PROMPTS


def _make(name: str, description: str, prompt: str, tools: list, model_name: str) -> dict:
    return {
        "name": name,
        "description": description,
        "system_prompt": prompt,
        "tools": tools,
        "model": get_llm(model_name),
    }


SUBAGENTS: list[dict] = [
    _make(
        name="researcher",
        description=(
            "Explore the repo or external docs for context. "
            "Use FIRST when the task needs codebase understanding, "
            "library API lookup, or example patterns."
        ),
        prompt=SUBAGENT_PROMPTS["researcher"],
        tools=[search_codebase_tool, search_docs_tool, read_file_tool],
        model_name="claude-haiku-4-5-20251001",
    ),
    _make(
        name="tester",
        description=(
            "Write or run tests. Use AFTER implementation, or when fixing a "
            "failure, to verify with `make test` and `make lint`."
        ),
        prompt=SUBAGENT_PROMPTS["tester"],
        tools=[read_file_tool, write_file_tool, run_tests_tool, lint_tool],
        model_name="claude-haiku-4-5-20251001",
    ),
    _make(
        name="reviewer",
        description=(
            "Review the recent diff or touched files for correctness, "
            "performance, security, and adherence to project conventions. "
            "Use BEFORE claiming the task is done."
        ),
        prompt=SUBAGENT_PROMPTS["reviewer"],
        tools=[read_file_tool, search_codebase_tool, lint_tool],
        model_name="claude-haiku-4-5-20251001",
    ),
]
