"""{{ cookiecutter.agent_pascal }} —— 提示词 / 工具 静态测试。"""

from {{ cookiecutter.agent_slug }}.prompts import SYSTEM_PROMPT, SUBAGENT_PROMPTS


def test_system_prompt_has_required_sections():
    """主提示词必须包含：mission / principles / constraints。"""
    for key in ("Operating Principles", "Constraints", "Output Format"):
        assert key in SYSTEM_PROMPT, f"missing section: {key}"


def test_subagent_prompts_present():
    for name in ("researcher", "tester", "reviewer"):
        assert name in SUBAGENT_PROMPTS
        assert len(SUBAGENT_PROMPTS[name]) > 20


def test_no_push_in_prompt():
    """主提示必须显式 'No auto-push'。"""
    assert "auto-push" in SYSTEM_PROMPT.lower() or "auto push" in SYSTEM_PROMPT.lower()
