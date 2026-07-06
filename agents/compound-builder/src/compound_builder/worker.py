"""CompoundBuilder —— 单 unit 的 LLM + tools 执行器。

``executor`` / ``fixer`` 在 ``ATELIER_DRY_RUN != true`` 时调用本模块,
在 ``workdir`` 里真实读写文件、跑命令、commit。
"""
from __future__ import annotations

import json
import os
from typing import Any

from compound_builder.llm import get_llm, resolve_default_model
from compound_builder.progress import progress
from compound_builder.prompts import SYSTEM_PROMPT_EXECUTOR, SYSTEM_PROMPT_FIXER
from compound_builder.state import CompoundBuilderState
from compound_builder.tools import build_tools
from compound_builder.workdir_ctx import set_workdir

_WORKER_TOOL_NAMES = frozenset({
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "bash",
    "git_status",
    "git_diff",
    "git_commit",
    "run_tests",
    "discover_test_entry",
})


def is_dry_run() -> bool:
    return os.getenv("ATELIER_DRY_RUN", "false").lower() == "true"


def _unit_prompt(state: CompoundBuilderState, unit: dict[str, Any], *, mode: str) -> str:
    plan = state.get("plan") or {}
    lines = [
        f"workdir: {state.get('workdir', '.')}",
        f"plan title: {plan.get('title', '')}",
        f"unit id: {unit.get('id')}",
        f"unit title: {unit.get('title')}",
        f"files: {', '.join(unit.get('files') or []) or '(infer from plan)'}",
        f"approach:\n{unit.get('approach') or '(see plan)'}",
        f"test scenarios: {json.dumps(unit.get('test_scenarios') or [], ensure_ascii=False)}",
        f"verification: {unit.get('verification') or '(run full suite after changes)'}",
    ]
    if mode == "fix":
        lines.extend([
            "",
            "VALIDATION FAILED — Fixer mode (diagnose → fix):",
            "1. Read last_error; reproduce failure; trace causal chain before editing.",
            "2. Minimal fix; run related tests.",
            "3. **Required:** ``git_commit`` with message:",
            f"   fix(<scope>): {unit.get('id')} <root-cause one-liner>",
            "",
            f"last_error:\n{state.get('last_error') or '(none)'}",
        ])
    elif unit.get("is_fix_unit"):
        lines.extend([
            "",
            "FIX-UNIT mode — source of truth is this finding/fix-plan, not the original plan:",
            f"approach / suggested fix: {unit.get('approach') or '(see finding)'}",
            "",
            "TDD: add/adjust tests proving the fix, then implement.",
            "4. **Required:** ``git_commit`` with message:",
            f"   fix(<scope>): {unit.get('id')} <short description>",
        ])
    else:
        lines.extend([
            "",
            "Execute this unit with strict TDD:",
            "1. Write or update failing tests first (RED).",
            "2. Implement minimal code to pass (GREEN).",
            "3. Refactor if needed.",
            "4. Run the verification command (or full test suite).",
            "5. **Required:** call ``git_commit`` with message:",
            f"   feat(<scope>): {unit.get('id')} <short description>",
            "   (git_commit runs git add automatically).",
            "",
            "If you forget to commit, the orchestrator will auto-commit dirty files,",
            "but you should still commit explicitly before finishing.",
            "",
            "Do NOT push. Stay in workdir. Use tools only.",
        ])
    return "\n".join(lines)


def _last_ai_text(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("ai", "assistant"):
            content = getattr(msg, "content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def run_unit_worker(
    state: CompoundBuilderState,
    unit: dict[str, Any],
    *,
    mode: str = "execute",
) -> str:
    """在 workdir 内用 ReAct agent 执行(或修复)一个 unit。返回摘要文本。"""
    wd = set_workdir(state.get("workdir") or os.getcwd())
    uid = unit.get("id", "?")
    progress(
        f"{'fixer' if mode == 'fix' else 'executor'}: LLM+tools unit {uid} "
        f"({unit.get('title', '')[:60]}) …"
    )
    system = SYSTEM_PROMPT_FIXER if mode == "fix" else SYSTEM_PROMPT_EXECUTOR
    user = _unit_prompt(state, unit, mode=mode)

    from compound_builder.react_agent import build_react_agent

    tools = [t for t in build_tools() if t.name in _WORKER_TOOL_NAMES]
    model = get_llm()
    agent = build_react_agent(
        model,
        tools,
        prompt=f"{system}\n\nModel: {resolve_default_model()}\nWorkdir: {wd}",
    )
    try:
        result = agent.invoke(
            {"messages": [("user", user)]},
            config={"recursion_limit": int(os.getenv("ATELIER_WORKER_RECURSION_LIMIT", "40"))},
        )
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(str(e)) from e
    summary = _last_ai_text(result)
    progress(f"{'fixer' if mode == 'fix' else 'executor'}: unit {uid} done")
    return summary


__all__ = ["is_dry_run", "run_unit_worker"]
