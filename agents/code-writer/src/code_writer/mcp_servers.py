"""Code Writer —— MCP 服务器集中声明（项目级，硬规矩 8）。

绝对**不**读 `~/.config/claude/mcp.json`、`~/.claude/mcp.json` 等全局 MCP 配置。
所有 server 必须在本文件 `all_mcp_servers()` 显式声明，并按 `.env` 开关启用。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MCPServer:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    enabled: bool = True
    description: str = ""


def _getenv_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def all_mcp_servers() -> list[MCPServer]:
    if _getenv_bool("ATELIER_MCP_DISABLED", False):
        return []

    candidates: list[MCPServer] = []

    if _getenv_bool("ATELIER_MCP_GITHUB", False):
        candidates.append(MCPServer(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")},
            description="GitHub MCP server (PR/issue/file).",
        ))

    if _getenv_bool("ATELIER_MCP_DOCS", False):
        candidates.append(MCPServer(
            name="docs-langchain",
            command="npx",
            args=["-y", "@anthropic/mcp-server-fetch", "https://docs.langchain.com"],
            env={},
            description="LangChain docs fetch via mcp-server-fetch.",
        ))

    if _getenv_bool("ATELIER_MCP_FILESYSTEM", False):
        candidates.append(MCPServer(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", os.getenv("ATELIER_WORKDIR", "/tmp")],
            env={},
            description="受限的文件系统 MCP。",
        ))

    return [s for s in candidates if s.enabled and shutil.which(s.command)]


async def load_mcp_tools_async() -> list:
    """异步懒加载；本示例默认不开，靠 .env 触发。"""
    try:
        from langchain_mcp_adapters import load_mcp_tools
    except ImportError:
        return []

    servers = all_mcp_servers()
    if not servers:
        return []

    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    from langchain_mcp_adapters.sessions import ClientSession

    tools: list = []
    for s in servers:
        params = StdioServerParameters(command=s.command, args=list(s.args), env={**os.environ, **s.env})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools.extend(await load_mcp_tools(session))
    return tools
