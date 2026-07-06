"""reviewer_agent —— 探索 + 结构化收尾。"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from compound_builder.review_context import DimensionReviewResult, FindingItem
from compound_builder.reviewer_agent import (
    _REVIEWER_AGENT_TOOLS,
    run_structured_finalize,
    summarize_exploration_messages,
)
from compound_builder.tools import build_tools


def test_reviewer_agent_tool_whitelist():
    allowed = set(_REVIEWER_AGENT_TOOLS)
    assert allowed == {
        "read_file",
        "glob",
        "grep",
        "git_diff",
        "git_status",
    }
    names = {t.name for t in build_tools() if t.name in allowed}
    assert names == allowed


def test_summarize_exploration_messages_takes_ai_content():
    messages = [
        AIMessage(content="Read patch. Found issue in sorts/foo.py:12."),
        AIMessage(content="Also verified tests cover edge cases."),
    ]
    notes = summarize_exploration_messages(messages)
    assert "foo.py:12" in notes
    assert "edge cases" in notes


def test_run_structured_finalize_retries_with_error_feedback(monkeypatch):
    attempts = {"n": 0}

    class FakeStructured:
        def invoke(self, msgs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("line: Input should be a valid integer, got '14-16'")
            human = msgs[1].content
            assert "Previous structured output REJECTED" in human
            assert "14-16" in human
            return DimensionReviewResult(
                findings=[
                    FindingItem(
                        severity="p3",
                        file="sorts/foo.py",
                        line=14,
                        summary="verified sort behavior",
                    ),
                ],
            )

    class FakeModel:
        def with_structured_output(self, schema):
            return FakeStructured()

    monkeypatch.setattr(
        "compound_builder.reviewer_agent.get_llm",
        lambda *args, **kwargs: FakeModel(),
    )

    result = run_structured_finalize(
        "testing",
        manifest="workdir: .",
        exploration_notes="checked foo.py",
        changed=["sorts/foo.py"],
        max_attempts=2,
    )
    assert attempts["n"] == 2
    assert result.findings[0].line == 14
