"""Unit 1: skills_loader.py 必须只接受项目级路径 (硬规矩 8)。

仅项目级路径;禁止读取 ~/.claude/skills、CLAUDE_CODE_SKILLS_DIR 等。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _fresh_import(name: str):
    if name in sys.modules:
        del sys.modules[name]
    return __import__(name, fromlist=["*"])


def test_skills_loader_module_exists():
    """skills_loader 必须存在。"""
    from modem_log_analyzer import skills_loader  # noqa: F401


def test_skills_loader_rejects_global_claude_path(monkeypatch):
    """强制把本地路径指向 ~/.claude/skills 必须被 RuntimeError 拒绝。"""
    monkeypatch.setenv(
        "MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR",
        str(Path.home() / ".claude" / "skills"),
    )
    sl = _fresh_import("modem_log_analyzer.skills_loader")
    with pytest.raises(RuntimeError, match="REFUSED|global|项目|outside|绝"):
        sl.all_skill_sources()


def test_skills_loader_default_local_only():
    """默认只接受项目内 ./skills/。"""
    os.environ.pop("MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR", None)
    os.environ.pop("MODEM_LOG_ANALYZER_SKILLS_GITHUB", None)
    sl = _fresh_import("modem_log_analyzer.skills_loader")
    sources = sl.all_skill_sources()
    kinds = {getattr(s, "kind", "") for s in sources}
    assert kinds <= {"dir", "github"}, f"禁止 kind={kinds}"


def test_skills_loader_has_assert_project_local():
    """反向断言:必须显式有 _assert_project_local 之类的边界检查。"""
    from modem_log_analyzer import skills_loader

    src = Path(skills_loader.__file__).read_text()
    assert "_assert_project_local" in src or "forbidden_substrings" in src, (
        "skills_loader 缺少项目级边界检查"
    )
    # 必须提及 .claude/skills 或 CLAUDE_CODE_SKILLS_DIR 的反向断言
    assert ".claude/skills" in src or "CLAUDE_CODE_SKILLS_DIR" in src
