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
GATEWAY_API = WORKSPACE_ROOT / "gateway" / "api"
GATEWAY_ROOT = WORKSPACE_ROOT / "gateway"

for p in (SRC, LIB_SRC, GATEWAY_API, GATEWAY_ROOT, WORKSPACE_ROOT):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

os.environ.setdefault("ANTHROPIC_API_KEY", "test-no-key")
# Plan U5: 合成 e2e 用规则管线, 不打真实 LLM
os.environ.setdefault("MODEM_LOG_ANALYZER_CLI_FORCE_RULES", "1")
# Plan U5: 让 FORCE_RULES 守卫放行测试/合成路径
os.environ.setdefault("ATELIER_ENV", "test")


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="needs LLM key; set ANTHROPIC_API_KEY")
    for item in items:
        if "llm" in item.keywords and not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
            item.add_marker(skip_llm)
