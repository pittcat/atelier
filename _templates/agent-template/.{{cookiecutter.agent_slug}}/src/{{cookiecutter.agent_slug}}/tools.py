"""{{ cookiecutter.agent_pascal }} 的工具集。

Main agent 用以下工具：
  - bash                  受限 shell（走 interrupt + allowlist）
  - read_file / write_file / edit_file
  - git_commit             （强制不允许 push）

如果需要 GitHub / docs MCP，把它们挂到 ``_mcp_tools()`` 里。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from common.tools.shell import bash_tool
from common.tools.fs import read_file, write_file, edit_file
from common.tools.git import git_commit, git_diff, git_status


def _git_tools() -> list[BaseTool]:
    """git 工具集。注意：默认不暴露 git_push，永远人工。"""
    return [git_status, git_diff, git_commit]


{% if cookiecutter.include_mcp_github == "yes" -%}
def _mcp_github_tools():
    """可选：GitHub MCP 工具。需要在 ~/.config/claude/mcp.json 配 token。"""
    from langchain_mcp_adapters import load_mcp_tools
    # 启动时由 mcp_servers 加载
    return []
{% endif -%}


def build_tools() -> list[BaseTool]:
    """主代理可用工具的合集。

    与 AGENTS.md 规则一致：
      - bash 必须配 interrupt_on
      - 不开 auto-push（git_push 永远不注册）
      - 子代理工具在 subagents.py 里独立声明
    """
    tools: list[BaseTool] = [
        # ---- 文件 ----
        read_file, write_file, edit_file,
        # ---- shell ----
        bash_tool,
        # ---- git ----
        *_git_tools(),
    ]
    {% if cookiecutter.include_mcp_github == "yes" -%}
    tools += _mcp_github_tools()
    {% endif -%}
    return tools
