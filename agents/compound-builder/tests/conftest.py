"""所有 Agent 测试的 conftest。

- 自动注入 PYTHONPATH，使 `from <agent_slug>.agent import agent` 可用
- 不连真实 LLM；如需 LLM，标记 @pytest.mark.llm
"""

import os
import sys
from pathlib import Path

import pytest

# 把 src/ 和项目 libs/ 加进 sys.path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORKSPACE_ROOT = ROOT.parent.parent.parent  # atelier/
LIB_SRC = WORKSPACE_ROOT / "libs" / "common" / "src"

for p in (SRC, LIB_SRC):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

# 默认无 key 环境:跳过需要 LLM 的测试
os.environ.setdefault("ANTHROPIC_API_KEY", "test-no-key")

# compound-builder 集成测试:StateGraph 上 ``interrupt_before=executor / fixer``
# 在默认 build() 下会触发 LangGraph 的 HITL pause;agent.invoke 在未 resume 时
# 不会到达 terminal phase。集成测试不走真实 LangGraph Studio HITL,所以默认
# **关闭** interrupt,让 ``invoke`` 跑完整图。这一开关不影响 R10 的真实运行路径。
#
# 必须在 ``compound_builder.interrupts`` 被 import 之前设置。pytest 把 conftest
# 在 collection 阶段 import,这比测试模块早。但是 ``agent.py`` 顶层 import
# ``graph`` 再 import ``interrupts`` 会进一步 import。这里 ``os.environ`` 写
# 完之后,真正的 ``INTERRUPT_MAP`` 在 graph/interrupts 首次 import 时构造,会看到
# 本 env。
os.environ.setdefault("ATELIER_INTERRUPT_DEFAULT", "false")
os.environ.setdefault("ATELIER_DRY_RUN", "true")
os.environ.setdefault("ATELIER_QUIET", "true")

# 还需要 ``from compound_builder import graph`` 时 ``interrupt_before=None``:
# graph.py 顶部 import `INTERRUPT_MAP` 在模块级执行,若 INTERRUPT_MAP 已经 cache
# 为旧值,则 conftest 设的 env 失效。下面 patch 一行就好。
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _force_no_interrupt_in_tests(monkeypatch):
    """集成测试一律强制 ATELIER_INTERRUPT_DEFAULT=false 并重建 INTERRUPT_MAP。

    原因:`compound_builder.interrupts.INTERRUPT_MAP` 是模块级 cache,不能
    直接 mutate 通过 env;必须重新触发 ``build_interrupt_map()`` 后再赋回。
    """
    monkeypatch.setenv("ATELIER_INTERRUPT_DEFAULT", "false")
    try:
        from compound_builder import interrupts as _intr
        from compound_builder.interrupts import build_interrupt_map
        _intr.INTERRUPT_MAP = build_interrupt_map()
        yield
    except ImportError:
        yield


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="needs LLM key; set ANTHROPIC_API_KEY")
    for item in items:
        if "llm" in item.keywords and not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
            item.add_marker(skip_llm)
