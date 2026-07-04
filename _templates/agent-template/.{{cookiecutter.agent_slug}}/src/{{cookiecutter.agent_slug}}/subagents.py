"""{{ cookiecutter.agent_pascal }} 的子代理清单。

按 AGENTS.md 规则：
  - 深度 ≤ 2（main → sub，禁止 sub-sub）
  - 每个 subagent 单一职责
  - subagent 不互相调用
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from {{ cookiecutter.agent_slug }}.prompts import SUBAGENT_PROMPTS
from common.subagent import make_subagent


def _read_only_tools() -> list[BaseTool]:
    """researcher 只读工具：检索代码 / 文档。"""
    from common.tools.search import search_codebase, search_docs
    return [search_codebase, search_docs]


def _tester_tools() -> list[BaseTool]:
    """tester 工具：写测试 + 跑测试 + 读代码。"""
    from common.tools.tester import write_file, read_file, run_tests
    return [read_file, write_file, run_tests]


def _reviewer_tools() -> list[BaseTool]:
    """reviewer 工具：只读 review。"""
    from common.tools.readonly import read_file, search_codebase, run_lint
    return [read_file, search_codebase, run_lint]


# =========================================
# Sub-agent 清单（main agent 用 task(...) 委派）
# =========================================
SUBAGENTS: list[dict] = [
    make_subagent(
        name="researcher",
        description=(
            "Explore the repository and external docs to gather context. "
            "Use FIRST when the task needs codebase understanding, "
            "library API lookup, or example patterns."
        ),
        prompt=SUBAGENT_PROMPTS["researcher"],
        tools=_read_only_tools(),
        model_name="{{ cookiecutter.model_subagent }}",
    ),
    make_subagent(
        name="tester",
        description=(
            "Write or run tests for the implemented code. "
            "Use AFTER implementation to verify with `make test` and `make lint`."
        ),
        prompt=SUBAGENT_PROMPTS["tester"],
        tools=_tester_tools(),
        model_name="{{ cookiecutter.model_subagent }}",
    ),
    make_subagent(
        name="reviewer",
        description=(
            "Review the recent diff or touched files for correctness, "
            "performance, security, and adherence to project conventions. "
            "Use BEFORE claiming a task is done."
        ),
        prompt=SUBAGENT_PROMPTS["reviewer"],
        tools=_reviewer_tools(),
        model_name="{{ cookiecutter.model_subagent }}",
    ),
]
