"""ModemLogAnalyzer —— CLI / 本地运行时的 .env 解析。

加载顺序（与 code-writer / compound-builder 对齐，slug 换成 modem-log-analyzer）:
  1. ``$ATELIER_HOME/.env``
  2. ``~/.atelier/modem-log-analyzer/.env``
  3. ``agents/modem-log-analyzer/.env``（源码模式）
  4. 仓库根 ``.env``（已安装倒推）

不在 ``agent.py`` 模块级调用，避免 langgraph-api 进程重复覆盖平台 env。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_AGENT_SLUG = "modem-log-analyzer"
_PKG_MODULE = "modem_log_analyzer"

_HERE = Path(__file__).resolve()
_PKG_PARENT = _HERE.parent  # modem_log_analyzer/
_SRC_PARENT = _HERE.parents[1]  # src/
_AGENT_PARENT = _HERE.parents[2]  # modem-log-analyzer/
_REPO_PARENT = _HERE.parents[3]  # atelier/


def resolve_dotenv_path() -> Path | None:
    """返回第一个存在的 .env 路径,无则 None。"""
    atelier_home = os.environ.get("ATELIER_HOME")
    if atelier_home:
        p = Path(atelier_home).expanduser() / ".env"
        if p.is_file():
            return p

    p = Path(f"~/.atelier/{_AGENT_SLUG}/.env").expanduser()
    if p.is_file():
        return p

    candidate = _AGENT_PARENT / ".env"
    if candidate.is_file():
        return candidate

    candidate = _REPO_PARENT / ".env"
    if candidate.is_file():
        return candidate

    return None


def load_cli_env(*, override: bool = False) -> Path | None:
    """加载 .env 到 ``os.environ``;返回实际使用的路径。

    默认 ``override=False``: shell / direnv 已导出的变量优先,不会被 .env 覆盖。
    """
    path = resolve_dotenv_path()
    if path is not None:
        load_dotenv(path, override=override)
        return path
    # 无 .env 文件时直接沿用当前 shell 环境
    if os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY"):
        print("[cli] no .env file; using shell environment (ANTHROPIC_* detected)", file=sys.stderr)
    else:
        print(
            f"[cli] WARN: no .env and no ANTHROPIC_* in shell. "
            f"Use direnv, export, or ~/.atelier/{_AGENT_SLUG}/.env",
            file=sys.stderr,
        )
    return None


__all__ = ["load_cli_env", "resolve_dotenv_path"]
