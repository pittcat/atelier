"""Code Writer —— 提示词静态测试。"""

from code_writer.prompts import SYSTEM_PROMPT, SUBAGENT_PROMPTS


def test_main_prompt_has_sections():
    for key in ("Operating Principles", "Anti-patterns", "Output Format"):
        assert key in SYSTEM_PROMPT


def test_three_subagents_present():
    for name in ("researcher", "tester", "reviewer"):
        assert name in SUBAGENT_PROMPTS


def test_no_push_clause():
    """主提示必须显式禁止 push。"""
    assert "push" in SYSTEM_PROMPT.lower()


def test_anti_patterns_listed():
    assert "deleting tests" in SYSTEM_PROMPT.lower() or "delete tests" in SYSTEM_PROMPT.lower()
