"""Code Writer Agent 的工具集。

主代理可用：
  - read_file / write_file / edit_file
  - bash（受限 + 人工批准）
  - git_status / git_diff / git_commit
注意：不暴露 git_push 永远人工。
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool

# 工作区根：默认 cwd；从 env ATELIER_WORKDIR 覆盖
WORKDIR = Path(os.getenv("ATELIER_WORKDIR", os.getcwd())).resolve()

# bash 白名单：跨进程持久
_BASH_ALLOWLIST_DEFAULT = {
    "ls", "cat", "rg", "fd", "find", "grep",
    "git", "diff", "log", "status",
    "python", "python3",
    "make", "pytest", "ruff", "mypy", "node", "npm", "uv",
    "echo", "head", "tail", "wc",
}


def _resolve(path: str) -> Path | str:
    """解析路径;若逃逸 workdir,返回 'ERROR: path escapes workdir: <path>' 字符串。

    返回 string 而不是 raise —— 与本文件其他工具(bash_tool 等)保持一致,
    也避免 langchain_core @tool 装饰器把 raise 当作工具错误。
    """
    p = (WORKDIR / path).resolve()
    if WORKDIR not in p.parents and p != WORKDIR:
        return f"ERROR: path escapes workdir: {path}"
    return p


# ============================================================
# 文件工具
# ============================================================

@tool
def read_file_tool(path: str, limit: int = 400) -> str:
    """Read a UTF-8 text file. Refuses paths outside the workdir."""
    p = _resolve(path)
    if isinstance(p, str):
        return p  # _resolve 报错字符串
    if not p.exists():
        return f"NOT FOUND: {p}"
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[:limit]) + (f"\n... ({len(lines)} lines total)" if len(lines) > limit else "")


@tool
def write_file_tool(path: str, content: str) -> str:
    """Write a file (overwriting). The agent system MUST require human approval before this."""
    p = _resolve(path)
    if isinstance(p, str):
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {p} ({len(content)} chars)"


@tool
def edit_file_tool(path: str, old_text: str, new_text: str) -> str:
    """Replace `old_text` with `new_text` in `path`. Fails if not unique."""
    p = _resolve(path)
    if isinstance(p, str):
        return p
    text = p.read_text(encoding="utf-8")
    if text.count(old_text) != 1:
        return f"ERROR: old_text appears {text.count(old_text)} times; needs to be unique."
    p.write_text(text.replace(old_text, new_text), encoding="utf-8")
    return f"edited {p}"


# ============================================================
# Shell 工具
# ============================================================

@tool
def bash_tool(command: str) -> str:
    """Run a bash command under the workdir.

    白名单 + 超时 60s。dangerous 的子命令（rm -rf, >, etc.）拒绝。
    中断：interrupt_on 强制人工批准。
    """
    forbidden = ["rm -rf", "rm -fr", ":(){:|:&};:", "mkfs", "dd if=", "shutdown", "reboot"]
    lower = command.lower()
    for bad in forbidden:
        if bad in lower:
            return f"BLOCKED: contains forbidden pattern '{bad}'"

    try:
        args = shlex.split(command)
    except ValueError as e:
        return f"PARSE ERROR: {e}"

    if not args:
        return "EMPTY"
    if args[0] not in _BASH_ALLOWLIST_DEFAULT:
        return f"NOT IN ALLOWLIST: '{args[0]}'; add it to _BASH_ALLOWLIST_DEFAULT to enable."

    try:
        cp = subprocess.run(
            args,
            cwd=str(WORKDIR),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT (60s)"

    out = (cp.stdout or "") + (cp.stderr or "")
    return out[-4000:] if len(out) > 4000 else out


# ============================================================
# Git 工具（不允许 push）
# ============================================================

@tool
def git_status_tool() -> str:
    """git status --porcelain=v1."""
    cp = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=20,
    )
    return (cp.stdout or "") + (cp.stderr or "")


@tool
def git_diff_tool(stat: bool = False) -> str:
    """git diff (or --stat)."""
    args = ["git", "diff"]
    if stat:
        args.append("--stat")
    cp = subprocess.run(args, cwd=str(WORKDIR), capture_output=True, text=True, timeout=20)
    out = (cp.stdout or "") + (cp.stderr or "")
    return out[-4000:] if len(out) > 4000 else out


@tool
def git_commit_tool(message: str) -> str:
    """git add -A + git commit with given message. Conventional-commits encouraged.

    HUMAN APPROVAL REQUIRED via interrupt_on.
    """
    if not message or len(message.strip()) < 8:
        return "ERROR: commit message too short"
    if len(message) > 200:
        return "ERROR: commit message too long (>200)"

    subprocess.run(["git", "add", "-A"], cwd=str(WORKDIR), check=False, timeout=30)
    cp = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=30,
    )
    return ((cp.stdout or "") + (cp.stderr or ""))[-2000:]


# ============================================================
# 测试 / Lint 工具（subagents 用）
# ============================================================

@tool
def run_tests_tool(path: str = "tests") -> str:
    """Run pytest under `path` (relative to workdir)."""
    cp = subprocess.run(
        ["pytest", "-q", path],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=300,
    )
    out = (cp.stdout or "") + (cp.stderr or "")
    return out[-6000:] if len(out) > 6000 else out


@tool
def lint_tool(path: str = ".") -> str:
    """Run ruff check on path."""
    cp = subprocess.run(
        ["ruff", "check", path],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=60,
    )
    return ((cp.stdout or "") + (cp.stderr or ""))[-4000:]


# ============================================================
# 检索工具（subagents 用）
# ============================================================

@tool
def search_codebase_tool(query: str, glob: str = "*", limit: int = 30) -> str:
    """ripgrep search in code."""
    cp = subprocess.run(
        ["rg", "--line-number", "--no-heading", "-g", glob, "--", query],
        cwd=str(WORKDIR), capture_output=True, text=True, timeout=30,
    )
    out = (cp.stdout or "")
    lines = out.splitlines()
    return "\n".join(lines[:limit]) + (f"\n... ({len(lines)} matches)" if len(lines) > limit else "")


@tool
def search_docs_tool(query: str) -> str:
    """Placeholder external docs lookup.

    Replace with real doc provider (e.g. mcp__docs) when wired.
    """
    return f"docs_lookup({query!r}) — implement via MCP when ready"


# ============================================================
# 工厂：主代理工具集
# ============================================================

def build_tools() -> list[BaseTool]:
    """主代理可用工具合集。注意：git_push 不在这里。"""
    return [
        # 文件
        read_file_tool, write_file_tool, edit_file_tool,
        # shell
        bash_tool,
        # git
        git_status_tool, git_diff_tool, git_commit_tool,
        # 测试 + 检索（main 也常用）
        run_tests_tool, search_codebase_tool,
    ]
