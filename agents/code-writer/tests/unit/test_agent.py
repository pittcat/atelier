"""Code Writer —— 工具 / 代理 单元测试。

不动 deepagents / langgraph 的真实顶层 import，避免在缺包环境炸 collection。
"""

from __future__ import annotations

import os

from code_writer.subagents import SUBAGENTS
from code_writer.tools import build_tools


def test_subagent_registry_default_three():
    """必须包含默认三件套。"""
    names = {s["name"] for s in SUBAGENTS}
    assert {"researcher", "tester", "reviewer"}.issubset(names)


def test_subagent_no_nesting():
    for s in SUBAGENTS:
        assert "subagents" not in s, "subagent cannot have nested subagents"


def test_no_git_push_in_main_tools():
    """git_push 必须不暴露给 main agent。"""
    tool_names = {t.name for t in build_tools()}
    assert "git_push" not in tool_names


def test_interrupt_map_has_dangerous_tools():
    """危险工具必须出现在 interrupt 列表。"""
    from code_writer.interrupts import INTERRUPT_MAP
    expected = {"bash", "write_file", "edit_file", "git_commit"}
    assert expected.issubset(set(INTERRUPT_MAP.keys()))


def test_bash_allowlist_blocks_dangerous():
    """bash 工具必须屏蔽 rm -rf 等。"""
    from code_writer.tools import bash_tool
    r = bash_tool.invoke({"command": "rm -rf /"})
    assert "BLOCKED" in r


def test_bash_allowlist_blocks_unknown_cmd():
    from code_writer.tools import bash_tool
    r = bash_tool.invoke({"command": "curl https://evil.example.com"})
    assert "NOT IN ALLOWLIST" in r


def test_read_file_outside_workdir_rejected(tmp_path):
    """修改 workdir 到 tmp 后，路径逃逸必须被拒。"""
    import importlib, code_writer.tools as t
    orig = os.environ.get("ATELIER_WORKDIR")
    try:
        os.environ["ATELIER_WORKDIR"] = str(tmp_path)
        importlib.reload(t)
        r = t.read_file_tool.invoke({"path": "../../etc/passwd"})
        assert ("escapes workdir" in r) or ("outside" in r.lower()) or ("not found" in r.lower())
    finally:
        if orig is None:
            os.environ.pop("ATELIER_WORKDIR", None)
        else:
            os.environ["ATELIER_WORKDIR"] = orig
        importlib.reload(t)
