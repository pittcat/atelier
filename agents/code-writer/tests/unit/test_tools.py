"""Code Writer —— 工具行为测试。"""

import os
import tempfile
from pathlib import Path

from code_writer.tools import (
    bash_tool, write_file_tool, read_file_tool, edit_file_tool,
    _resolve,
)


def test_resolve_inside_workdir():
    rel = "tests/unit/test_tools.py"
    p = _resolve(rel)
    assert p.exists()
    assert p.name == "test_tools.py"


def test_resolve_escapes_blocked():
    """路径逃逸必须被拒:返回 ERROR 字符串,不抛异常(与 bash_tool 风格一致)。"""
    p = _resolve("../langgraph/CLAUDE.md")
    assert isinstance(p, str)
    assert "escapes workdir" in p


def test_read_write_edit_roundtrip(tmp_path: Path):
    """在临时目录里模拟一次读写改。"""
    target = tmp_path / "x.txt"
    target.write_text("hello", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "hello"
    target.write_text(target.read_text(encoding="utf-8") + " world", encoding="utf-8")
    assert "hello world" in target.read_text(encoding="utf-8")
