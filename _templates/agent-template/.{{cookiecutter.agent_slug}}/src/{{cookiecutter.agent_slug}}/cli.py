"""{{ cookiecutter.agent_pascal }} 的命令行入口。

支持：
    python -m {{ cookiecutter.agent_slug }}.cli run "实现 X 功能"
    python -m {{ cookiecutter.agent_slug }}.cli replay <thread_id>
"""

from __future__ import annotations

import sys

import click

from {{ cookiecutter.agent_slug }}.agent import agent


@click.group()
def cli() -> None:
    """Atelier {{ cookiecutter.agent_pascal }} CLI."""


@cli.command()
@click.argument("prompt")
@click.option("--thread", default=None, help="thread_id；相同 ID 维持对话。")
def run(prompt: str, thread: str | None) -> None:
    """Run the agent with a prompt."""
    import uuid
    cfg = {"configurable": {"thread_id": thread or str(uuid.uuid4())}}
    for event in agent.stream({"messages": [("user", prompt)]}, config=cfg):
        print(event)
        sys.stdout.flush()


@cli.command()
@click.argument("thread_id")
def replay(thread_id: str) -> None:
    """Replay all states of a thread."""
    cfg = {"configurable": {"thread_id": thread_id}}
    for state in agent.get_state_history(cfg):
        print(f"[{state.created_at}] next={state.next}")
        for m in state.values.get("messages", []):
            print(f"  {m.type}: {(m.content or '')[:200]}")


if __name__ == "__main__":
    cli()
