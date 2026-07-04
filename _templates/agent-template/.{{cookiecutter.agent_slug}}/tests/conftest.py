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

# 默认无 key 环境：跳过需要 LLM 的测试
os.environ.setdefault("ANTHROPIC_API_KEY", "test-no-key")


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="needs LLM key; set ANTHROPIC_API_KEY")
    for item in items:
        if "llm" in item.keywords and not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
            item.add_marker(skip_llm)
