"""命令行入口。

    python -m code_writer.cli run "为 X 加一个新接口"
    python -m code_writer.cli replay <thread_id>
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import click
from dotenv import load_dotenv

# 提前 load .env,override=True 强制覆盖 shell 残留 env(用户 ~/.zshrc 或者
# CC Switch 注入的 ANTHROPIC_BASE_URL=http://127.0.0.1:15721 之类的旧代理 env)。
# 路径计算:cli.py 在 src/code_writer/cli.py,所以 _ROOT 应该是 parents[2]
#   parents[0] = code_writer/
#   parents[1] = src/
#   parents[2] = code-writer/  ← 这就是 _ROOT
_ROOT = Path(__file__).resolve().parents[2]   # agents/code-writer/
_dotenv_path = _ROOT / ".env"
load_dotenv(_dotenv_path, override=True)

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
