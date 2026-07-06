"""validator_agent —— 工具白名单。"""
from __future__ import annotations

from compound_builder.tools import build_tools
from compound_builder.validator_agent import _VALIDATOR_AGENT_TOOLS


def test_validator_agent_tool_whitelist():
    allowed = set(_VALIDATOR_AGENT_TOOLS)
    assert allowed == {
        "read_file",
        "glob",
        "grep",
        "git_diff",
        "git_status",
        "bash",
        "discover_test_entry",
        "run_tests",
    }
    names = {t.name for t in build_tools() if t.name in allowed}
    assert names == allowed
