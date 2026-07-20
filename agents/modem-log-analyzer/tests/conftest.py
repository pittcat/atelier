"""modem-log-analyzer 测试 conftest。

- 自动注入 src/ 和 libs/common 到 sys.path
- 默认无 LLM key
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORKSPACE_ROOT = ROOT.parent.parent.parent  # atelier/
LIB_SRC = WORKSPACE_ROOT / "libs" / "common" / "src"

for p in (SRC, LIB_SRC):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

os.environ.setdefault("ANTHROPIC_API_KEY", "test-no-key")


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="needs LLM key; set ANTHROPIC_API_KEY")
    for item in items:
        if "llm" in item.keywords and not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
            item.add_marker(skip_llm)
