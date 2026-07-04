"""命令行入口。

    python -m code_writer.cli run "为 X 加一个新接口"
    python -m code_writer.cli replay <thread_id>
"""

from __future__ import annotations

import sys
import uuid

import click

from code_writer.agent import agent


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
