"""ModemLogAnalyzer —— MCP 服务器声明与加载。

硬规矩 8：**不允许**从 `~/.config/claude/mcp.json`、`~/.claude/mcp.json` 等任何
"用户级 / 全局级"MCP 配置文件加载。所有 MCP server 必须在本文件 `all_mcp_servers()`
里显式声明，并在 `.env` 中给出凭据。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass
class MCPServer:
    name: str  # 例如 "github"  -> 工具前缀 mcp__github__*
    command: str  # 例如 "npx"
    args: list[str]
    env: dict[str, str]
    enabled: bool = True
    description: str = ""


def _getenv_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def all_mcp_servers() -> list[MCPServer]:
    """返回所有声明的 MCP server，可被 main / sub-agent 工具集复用。

    严格按硬规矩 8：只接受本文件显式声明的 server + 环境变量开关。
    不会去读 `~/.config/claude/mcp.json` 等全局 MCP 配置。
    """
    if _getenv_bool("MODEM_LOG_ANALYZER_MCP_DISABLED", False):
        return []

    servers: list[MCPServer] = []

    return [s for s in servers if s.enabled and shutil.which(s.command)]


async def load_mcp_tools_async() -> list:
    """懒加载 MCP server → langchain 工具列表。

    异步入口（langchain-mcp-adapters 是异步的）。
    """
    try:
        from langchain_mcp_adapters import load_mcp_tools
    except ImportError:
        return []

    servers = all_mcp_servers()
    if not servers:
        return []

    from langchain_mcp_adapters.sessions import ClientSession
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    tools: list = []
    for s in servers:
        params = StdioServerParameters(
            command=s.command,
            args=list(s.args),
            env={**os.environ, **s.env},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools.extend(await load_mcp_tools(session))
    return tools
