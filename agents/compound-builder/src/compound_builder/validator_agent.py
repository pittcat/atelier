"""Validator Agent —— 独立 ReAct Agent(LLM + 只读工具 + 跑测试)。

与 executor/fixer 的 ``worker.py`` 同级:**不是**外层 Compound Builder StateGraph 的
编排节点;外层 ``nodes/validator.py`` 只负责 commit gate + 写 ``test.passed/failed``。

本 Agent 必须自己读仓库(AGENTS.md / README / pyproject / CI)再决定全量测试命令,
对齐 ralph ``ce-executor-serial`` 的 validator hat。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from compound_builder.llm import get_llm, resolve_default_model
from compound_builder.progress import progress
from compound_builder.prompts import SYSTEM_PROMPT_VALIDATOR
from compound_builder.state import CompoundBuilderState
from compound_builder.tools import build_tools
from compound_builder.workdir_ctx import set_workdir

# 只读探索 + 执行测试;禁止改代码 / commit
_VALIDATOR_AGENT_TOOLS = frozenset({
    "read_file",
    "glob",
    "grep",
    "git_diff",
    "git_status",
    "bash",
    "discover_test_entry",
    "run_tests",
})

_TEST_CMD_RE = re.compile(
    r"pytest|make\s+test|cargo\s+test|npm\s+test|go\s+test|"
    r"python\s+-m\s+pytest|tox|nox|ctest|mvn\s+test|gradle\s+test",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    command: str
    output_tail: str


def _content_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _parse_bash_exit(content: str) -> int | None:
    match = re.search(r"\[bash exit=(\d+)\]", content)
    return int(match.group(1)) if match else None


def _parse_run_tests_json(content: str) -> tuple[int | None, str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None, ""
    rc = payload.get("returncode")
    entry = str(payload.get("entry") or "")
    return (int(rc) if rc is not None else None), entry


def _looks_like_test_command(command: str) -> bool:
    return bool(_TEST_CMD_RE.search(command))


def extract_validation_from_messages(messages: list[Any]) -> ValidationResult | None:
    """从 Agent 消息历史取**最后一次**全量测试命令的真实 exit code。"""
    pending: dict[str, str] = {}
    last: ValidationResult | None = None

    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = str(tc.get("name") or "")
                args = tc.get("args") or {}
                tid = str(tc.get("id") or "")
            else:
                name = str(getattr(tc, "name", "") or "")
                args = getattr(tc, "args", {}) or {}
                tid = str(getattr(tc, "id", "") or "")
            if name == "bash":
                pending[tid] = str(args.get("command") or "bash")
            elif name == "run_tests":
                entry = args.get("entry")
                pending[tid] = str(entry) if entry else "run_tests(auto)"

        msg_type = getattr(msg, "type", None) or getattr(msg, "role", "")
        if msg_type not in ("tool", "tool_message"):
            continue

        name = str(getattr(msg, "name", "") or "")
        content = _content_str(getattr(msg, "content", ""))
        tid = str(getattr(msg, "tool_call_id", "") or "")
        command = pending.get(tid, name)

        if name == "bash":
            exit_code = _parse_bash_exit(content)
            if exit_code is None or not _looks_like_test_command(command):
                continue
            last = ValidationResult(
                passed=exit_code == 0,
                command=command,
                output_tail=content[-4000:],
            )
        elif name == "run_tests":
            exit_code, entry = _parse_run_tests_json(content)
            if exit_code is None:
                continue
            last = ValidationResult(
                passed=exit_code == 0,
                command=entry or command,
                output_tail=content[-4000:],
            )

    return last


def _validator_task_prompt(state: CompoundBuilderState, unit: dict[str, Any]) -> str:
    plan = state.get("plan") or {}
    plan_path = (state.get("plan_path") or "").strip()
    verification = (unit.get("verification") or "").strip()
    lines = [
        f"workdir: {state.get('workdir', '.')}",
        f"plan_path: {plan_path or '(unknown)'}",
        f"plan title: {plan.get('title', '')}",
        f"unit id: {unit.get('id')}",
        f"unit title: {unit.get('title')}",
        f"unit files: {', '.join(unit.get('files') or []) or '(infer from plan)'}",
        f"test scenarios: {json.dumps(unit.get('test_scenarios') or [], ensure_ascii=False)}",
        "",
        "## Your mission (Validator Agent)",
        "",
        "You are an **autonomous validator agent**. You must **read the repo** and",
        "discover the canonical **full** test suite command — do NOT guess from memory.",
        "",
        "### Required exploration (read before running tests)",
        "1. ``read_file`` on AGENTS.md / CLAUDE.md / README.md (if present).",
        "2. ``read_file`` on Makefile, pyproject.toml, package.json, Cargo.toml.",
        "3. ``glob`` / ``grep`` for tests/ test_*.py conftest.py.",
        "4. ``git_diff`` / ``git_status`` optional — understand what changed.",
        "5. ``discover_test_entry`` is a **hint only** — verify cwd/import paths.",
        "",
        "Then run the **full** suite via ``bash`` or ``run_tests``.",
        "Pass/fail = tool exit code only. Do NOT edit source or commit.",
        "",
    ]
    if verification:
        lines.append(f"Plan verification hint (may be wrong): `{verification}`")
    if plan_path:
        lines.append(f"You may ``read_file`` the plan: `{plan_path}`")
    lines.extend([
        "",
        "Execute at least one full-suite test command before you stop.",
    ])
    return "\n".join(lines)


def build_validator_agent():
    """构造 Validator ReAct Agent(独立子图,由 ``run_validator_agent`` 调用)。"""
    from compound_builder.react_agent import build_react_agent

    tools = [t for t in build_tools() if t.name in _VALIDATOR_AGENT_TOOLS]
    model = get_llm()
    return build_react_agent(
        model,
        tools,
        prompt=SYSTEM_PROMPT_VALIDATOR,
    )


def run_validator_agent(
    state: CompoundBuilderState,
    unit: dict[str, Any],
) -> ValidationResult:
    """运行 Validator Agent;返回客观 pass/fail(基于 exit code)。"""
    wd = set_workdir(state.get("workdir") or os.getcwd())
    uid = unit.get("id", "?")
    progress(f"validator-agent: exploring + running full suite for unit {uid} …")

    agent = build_validator_agent()
    system_tail = (
        f"\n\nModel: {resolve_default_model()}\n"
        f"Workdir: {wd}\n"
        "Role: Validator Agent — read repo docs first, then run full test suite."
    )
    try:
        result = agent.invoke(
            {
                "messages": [
                    ("system", SYSTEM_PROMPT_VALIDATOR + system_tail),
                    ("user", _validator_task_prompt(state, unit)),
                ],
            },
            config={
                "recursion_limit": int(
                    os.getenv("ATELIER_VALIDATOR_RECURSION_LIMIT", "40")
                ),
            },
        )
    except Exception as e:  # noqa: BLE001
        return ValidationResult(
            passed=False,
            command="(validator-agent-error)",
            output_tail=f"validator agent crashed: {e}",
        )

    messages = result.get("messages") or []
    extracted = extract_validation_from_messages(messages)
    if extracted is None:
        return ValidationResult(
            passed=False,
            command="(none)",
            output_tail=(
                "validator agent finished without executing a full test suite "
                "via bash/run_tests"
            ),
        )
    progress(
        f"validator-agent: suite `{(extracted.command or '')[:80]}` "
        f"→ {'PASS' if extracted.passed else 'FAIL'}"
    )
    return extracted


# 向后兼容旧 import 路径
run_validator_worker = run_validator_agent

__all__ = [
    "ValidationResult",
    "build_validator_agent",
    "extract_validation_from_messages",
    "run_validator_agent",
    "run_validator_worker",
]
