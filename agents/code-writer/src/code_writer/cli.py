"""命令行入口。

两种调用方式:
  1. 在仓库里直接跑:  python -m code_writer.cli run "..."
       — .env 自动从 ../agents/code-writer/.env 加载(相对于源码位置)
       — WORKDIR = 当前 cwd
  2. 装成系统 CLI 后: code-writer run "..."
       — .env 加载顺序: $ATELIER_HOME/.env > ~/.atelier/code-writer/.env > <site-packages parent>/.env
       — WORKDIR = 当前 cwd(用户在哪个项目目录就改哪个项目)

    code-writer replay <thread_id>
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import click
from dotenv import load_dotenv

# Resolve .env 路径。优先级:
#   1. $ATELIER_HOME 环境变量(全局配置,推荐用于已安装的 CLI)
#   2. <package 源码位置>/../../../.env —— site-packages/code_writer/cli.py → 回到仓库根
#   3. <cli.py parents[2]>/.env —— 源码在 agents/code-writer/ 时直接定位
_HERE = Path(__file__).resolve()
_PKG_PARENT = _HERE.parents[1]   # code_writer/
_SRC_PARENT = _HERE.parents[2]   # src/  (when run from source)
_AGENT_PARENT = _HERE.parents[3]  # code-writer/  (when run from source)
_REPO_PARENT = _HERE.parents[4]   # atelier/   (when run from source)


def _resolve_dotenv_path() -> Path | None:
    # 1. 显式 ATELIER_HOME
    atelier_home = os.environ.get("ATELIER_HOME")
    if atelier_home:
        p = Path(atelier_home).expanduser() / ".env"
        if p.is_file():
            return p
    # 2. 全局默认 ~/.atelier/code-writer/.env
    p = Path.home() / ".atelier" / "code-writer" / ".env"
    if p.is_file():
        return p
    # 3. 源码运行模式:cli.py 在 src/code_writer/cli.py,所以 agents/code-writer/.env
    candidate = _AGENT_PARENT / ".env"
    if candidate.is_file():
        return candidate
    # 4. 已安装模式:从 site-packages 倒推 atelier 仓库根(假设标准 layout)
    candidate = _REPO_PARENT / ".env"
    if candidate.is_file():
        return candidate
    return None


_dotenv_path = _resolve_dotenv_path()
if _dotenv_path is not None:
    load_dotenv(_dotenv_path, override=True)
else:
    print(
        "[cli] WARN: .env not found. Set ATELIER_HOME or create "
        "~/.atelier/code-writer/.env, or run from agent source directory.",
        file=sys.stderr,
    )

# 重要:deepagents 0.6 默认 install AnthropicPromptCachingMiddleware,它无条件给
# ChatAnthropic payload 加 cache_control 字段。minimax 部分版本不接受这个字段
# → 502。把它的 wrap_model_call 改成 noop,跳过缓存控制注入。
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware  # noqa: E402

def _noop_wrap_model_call(self, request, handler):
    """Skip cache_control injection; just pass-through."""
    return handler(request)
AnthropicPromptCachingMiddleware.wrap_model_call = _noop_wrap_model_call  # type: ignore[assignment]

from code_writer.agent import agent  # noqa: E402  必须在 load_dotenv + patch 之后


@click.group()
def cli() -> None:
    """Code Writer CLI."""


@cli.command()
@click.argument("prompt")
@click.option("--thread", default=None, help="thread_id; same id → same conversation.")
def run(prompt: str, thread: str | None) -> None:
    """Run the agent with a prompt and stream events."""
    cfg = {"configurable": {"thread_id": thread or str(uuid.uuid4())}}
    for event in agent.stream({"messages": [("user", prompt)]}, config=cfg):
        print(event)
        sys.stdout.flush()


@cli.command()
@click.argument("thread_id")
def replay(thread_id: str) -> None:
    """Replay all states of a thread (for debugging)."""
    cfg = {"configurable": {"thread_id": thread_id}}
    for state in agent.get_state_history(cfg):
        ts = state.created_at
        nxt = state.next
        print(f"[{ts}] next={nxt}")
        for m in (state.values.get("messages") or []):
            content = (m.content if isinstance(m.content, str) else str(m.content))
            print(f"  {m.type}: {content[:200]}")


if __name__ == "__main__":
    cli()
