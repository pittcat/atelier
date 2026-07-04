"""测试 conftest: 自动注入 src/ 到 sys.path，默认无 LLM。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-no-key")


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="needs real LLM key")
    for item in items:
        if "llm" in item.keywords:
            if not os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-"):
                item.add_marker(skip_llm)
