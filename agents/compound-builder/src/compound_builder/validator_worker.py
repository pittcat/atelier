"""Validator —— LLM 搜索测试入口并跑全量套件;pass/fail 只看工具 exit code。"""
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

_VALIDATOR_TOOL_NAMES = frozenset({
    "read_file",
    "glob",
    "grep",
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
    """从 agent 消息历史取**最后一次**测试类 bash/run_tests 的真实 exit code。"""
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


def _validator_user_prompt(state: CompoundBuilderState, unit: dict[str, Any]) -> str:
    plan = state.get("plan") or {}
    verification = (unit.get("verification") or "").strip()
    lines = [
        f"workdir: {state.get('workdir', '.')}",
        f"plan title: {plan.get('title', '')}",
        f"unit id: {unit.get('id')}",
        f"unit title: {unit.get('title')}",
        f"unit files: {', '.join(unit.get('files') or []) or '(see plan)'}",
        f"test scenarios: {json.dumps(unit.get('test_scenarios') or [], ensure_ascii=False)}",
        "",
        "Your task: find how this repo runs its **full** automated test suite, then run it.",
        "Do NOT edit source files. Read/search first, then execute via bash or run_tests.",
        "",
    ]
    if verification:
        lines.append(
            f"Plan hint (may be wrong cwd/imports — verify): `{verification}`"
        )
    else:
        lines.append("Plan did not specify verification — discover from repo layout.")
    lines.extend([
        "",
        "You MUST execute at least one full-suite test command before finishing.",
        "Pass/fail is determined only from tool exit codes, not your summary.",
    ])
    return "\n".join(lines)


def run_validator_worker(
    state: CompoundBuilderState,
    unit: dict[str, Any],
) -> ValidationResult:
    """LLM 在 workdir 内搜索并跑全量测试;返回客观 ValidationResult。"""
    wd = set_workdir(state.get("workdir") or os.getcwd())
    uid = unit.get("id", "?")
    progress(f"validator: LLM discovering + running full test suite for unit {uid} …")

    from langgraph.prebuilt import create_react_agent

    tools = [t for t in build_tools() if t.name in _VALIDATOR_TOOL_NAMES]
    model = get_llm()
    agent = create_react_agent(
        model,
        tools,
        prompt=(
            f"{SYSTEM_PROMPT_VALIDATOR}\n\n"
            f"Model: {resolve_default_model()}\nWorkdir: {wd}"
        ),
    )
    result = agent.invoke(
        {"messages": [("user", _validator_user_prompt(state, unit))]},
        config={
            "recursion_limit": int(
                os.getenv("ATELIER_VALIDATOR_RECURSION_LIMIT", "30")
            ),
        },
    )
    messages = result.get("messages") or []
    extracted = extract_validation_from_messages(messages)
    if extracted is None:
        return ValidationResult(
            passed=False,
            command="(none)",
            output_tail="validator: no full test command was executed via bash/run_tests",
        )
    progress(
        f"validator: suite `{(extracted.command or '')[:80]}` "
        f"→ {'PASS' if extracted.passed else 'FAIL'}"
    )
    return extracted


__all__ = [
    "ValidationResult",
    "extract_validation_from_messages",
    "run_validator_worker",
]
