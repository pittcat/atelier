"""Code Writer —— 跨模块 / 状态 / 中断集成测试。

需要真实 LLM 时跑（带 @pytest.mark.llm）；默认离线跳过。
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.llm
def test_thread_state_persistence():
    """同 thread_id 续聊，状态应保留。"""
    pytest.skip("需要 LLM；本环境默认无 key，跳过")


@pytest.mark.llm
def test_interrupt_bash_resume():
    pytest.skip("需要 LLM + interrupt UI；本环境跳过")
