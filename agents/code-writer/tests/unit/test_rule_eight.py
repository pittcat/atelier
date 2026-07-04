"""硬规矩 #8 单元测试：仅项目级 skill，禁读 ~/.claude/skills 全局路径。

不依赖真实 LLM/MCP，纯 Python 校验。
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# ROOT = tests/unit -> parents[2] = agents/code-writer
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


# 模块级常量:用于"反向断言"。当源码出现禁用字符串(路径 / env 名字)时,
# 必须在否定词上下文中,否则视为违规。_ASSERT_KEYWORDS 列出允许的"否定语境"标志。
# 注意匹配的是原文(含 markdown 加粗 **),所以包含松散否定词。
_ASSERT_KEYWORDS = ("禁止", "不读", "绝不", "REFUSED", "拒绝", "不", "禁")


def _import(name: str):
    return importlib.import_module(name)


def test_default_skills_only_local():
    """默认（不设 env）只能拿到 ./skills/，且必须在项目内。"""
    os.environ.pop("ATELIER_SKILLS_GITHUB", None)
    os.environ.pop("ATELIER_LOCAL_SKILLS_DIR", None)

    sl = _import("code_writer.skills_loader")
    sources = sl.all_skill_sources()

    # 必须存在本地 ./skills/（示范 Agent 已建）
    assert any(s.label == "local" and s.kind == "dir" for s in sources), \
        "默认应拿到 ./skills/ 项目内 skills 源"

    # 没有"claude-code-skills" 这种全局源
    assert not any(getattr(s, "kind", "") == "claude_code" for s in sources), \
        "禁止 'claude_code' kind 全局 skills 源"


def test_reject_global_claude_skills_path(monkeypatch):
    """强制把本地路径指向 ~/.claude/skills 应当被 RuntimeError 拒绝。"""
    monkeypatch.setenv("ATELIER_LOCAL_SKILLS_DIR", str(Path.home() / ".claude" / "skills"))
    # 重新加载模块以让 env 影响
    if "code_writer.skills_loader" in sys.modules:
        del sys.modules["code_writer.skills_loader"]
    sl = _import("code_writer.skills_loader")
    with pytest.raises(RuntimeError, match="REFUSED"):
        sl.all_skill_sources()


def test_skills_loader_no_global_dependencies():
    """静态扫描：skills_loader.py 不应 import Path.home() / read ~/.claude/skills。"""
    txt = (SRC / "code_writer" / "skills_loader.py").read_text()
    # 真正"读 ~/.claude" 的代码不应存在
    assert 'Path.home() / ".claude"' not in txt
    # 反向断言字符串里出现是允许的，但必须出现在"禁止" / "不读" / "绝不" 等
    # 否定词上下文中。
    if "CLAUDE_CODE_SKILLS_DIR" in txt:
        assert any(k in txt for k in _ASSERT_KEYWORDS), (
            "CLAUDE_CODE_SKILLS_DIR mentioned but no 禁止/不读/绝不/REFUSED context"
        )
    # 所有加载必须经过 _assert_project_local 校验
    assert "_assert_project_local" in txt


def test_mcp_servers_no_global_config_read():
    """mcp_servers.py 不应读 ~/.config/claude/mcp.json 等全局 MCP 配置。"""
    txt = (SRC / "code_writer" / "mcp_servers.py").read_text()
    for bad in ("~/.config/claude", "~/.claude/mcp.json"):
        if bad in txt:
            assert any(k in txt for k in _ASSERT_KEYWORDS), (
                f"{bad} appears but is not within a 禁止/不读/绝不/REFUSED block"
            )
    # 必须显式声明 server 而不是 import 全局
    assert "all_mcp_servers" in txt
