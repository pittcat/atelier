"""validator_worker —— 从 agent 消息提取测试 exit code。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from compound_builder.validator_worker import (
    ValidationResult,
    extract_validation_from_messages,
)


def test_extract_last_bash_pytest():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "id": "tc1",
                "name": "bash",
                "args": {"command": "cd sorts && pytest -v"},
            }],
        ),
        ToolMessage(
            content="[bash exit=0]\nstdout:\n19 passed\nstderr:\n",
            tool_call_id="tc1",
            name="bash",
        ),
    ]
    result = extract_validation_from_messages(messages)
    assert result is not None
    assert result.passed is True
    assert "pytest" in result.command


def test_extract_failed_run_tests():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "id": "tc2",
                "name": "run_tests",
                "args": {"workdir": "."},
            }],
        ),
        ToolMessage(
            content='{"entry": "pytest", "returncode": 1, "stdout_tail": "FAILED", "stderr_tail": ""}',
            tool_call_id="tc2",
            name="run_tests",
        ),
    ]
    result = extract_validation_from_messages(messages)
    assert result is not None
    assert result.passed is False
    assert result.command == "pytest"


def test_ignores_non_test_bash():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "id": "tc3",
                "name": "bash",
                "args": {"command": "ls -la"},
            }],
        ),
        ToolMessage(
            content="[bash exit=0]\nstdout:\n.\nstderr:\n",
            tool_call_id="tc3",
            name="bash",
        ),
    ]
    assert extract_validation_from_messages(messages) is None


def test_uses_last_test_run():
    messages = [
        AIMessage(
            content="",
            tool_calls=[{
                "id": "a",
                "name": "bash",
                "args": {"command": "pytest -q"},
            }],
        ),
        ToolMessage(
            content="[bash exit=1]\nstdout:\nfail\nstderr:\n",
            tool_call_id="a",
            name="bash",
        ),
        AIMessage(
            content="",
            tool_calls=[{
                "id": "b",
                "name": "bash",
                "args": {"command": "cd sorts && pytest -v"},
            }],
        ),
        ToolMessage(
            content="[bash exit=0]\nstdout:\nok\nstderr:\n",
            tool_call_id="b",
            name="bash",
        ),
    ]
    result = extract_validation_from_messages(messages)
    assert result is not None
    assert result.passed is True
    assert "sorts" in result.command
