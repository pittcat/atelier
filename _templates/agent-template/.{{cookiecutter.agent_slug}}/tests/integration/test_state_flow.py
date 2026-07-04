"""{{ cookiecutter.agent_pascal }} —— 跨模块/状态/中断的集成测试。

需要在 GitHub 上有"分支 + PR"的模拟环境，生产里通常连真 GitHub。
本地默认跳过：``pytest -q -m "not integration"``。
"""

import pytest

pytestmark = pytest.mark.integration


def test_thread_state_persistence():
    """同 thread_id 续聊，状态应保留。"""
    # 留作占位；需要在 EVAL.md 跑通后接真数据
    pytest.skip("integration; enable after eval harness ready")
