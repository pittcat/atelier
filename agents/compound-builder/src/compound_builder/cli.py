"""CompoundBuilder —— CLI。

按 plan U5:
  - ``python -m compound_builder.cli run --plan <plan.md>``
  - ``python -m compound_builder.cli replay <thread_id>``
  - ``python -m compound_builder.cli verify <thread_id>``

``.env`` 在 import 业务模块前自动加载(见 ``env.load_cli_env``)。
``--workdir`` / ``--repo`` 默认当前 shell 的 cwd,并写入 ``ATELIER_WORKDIR``。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import click

from compound_builder.env import load_cli_env
from compound_builder.llm import resolve_default_model

# .env 必须先于 tracing / LLM 相关 import;shell/direnv 优先(override=False)
_dotenv_used = load_cli_env(override=False)

# MiniMax 等 anthropic-compat 服务可能拒绝 cache_control → 502
try:
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware  # noqa: E402

    def _noop_wrap_model_call(self, request, handler):  # noqa: ANN001
        return handler(request)

    AnthropicPromptCachingMiddleware.wrap_model_call = _noop_wrap_model_call  # type: ignore[method-assign]
except Exception:
    pass

from compound_builder import tracing  # noqa: E402
from compound_builder.agent import build_agent  # noqa: E402
from compound_builder.flow_verify import verify_flow  # noqa: E402
from compound_builder.progress import progress, progress_node  # noqa: E402


def _invoke_graph(graph, state: dict, cfg: dict, *, stream: bool) -> dict:
    """跑图;``stream=True`` 时每个节点完成打一行 stderr 进度。"""
    if not stream:
        return graph.invoke(state, config=cfg)

    progress("graph: streaming node updates (executor may take several minutes per unit)")
    for chunk in graph.stream(state, config=cfg, stream_mode="updates"):
        for node_name, node_patch in chunk.items():
            if isinstance(node_patch, dict):
                progress_node(node_name, node_patch)

    snap = graph.get_state(cfg)
    return dict(snap.values) if snap else state


def _resolve_workdir(workdir: str | None) -> Path:
    p = Path(workdir or os.getcwd()).resolve()
    os.environ["ATELIER_WORKDIR"] = str(p)
    return p


def _echo_verify(report, *, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo(report.format_human())


@click.group()
def cli() -> None:
    """Atelier CompoundBuilder CLI."""


@cli.command()
@click.option(
    "--plan",
    "plan_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="path to plan.md",
)
@click.option("--thread", default=None, help="thread_id;相同 ID 续接 LangGraph 状态。")
@click.option(
    "-w",
    "--workdir",
    "--repo",
    "workdir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="代码仓库根目录(默认:当前 shell cwd)",
)
@click.option(
    "--verify/--no-verify",
    default=True,
    help="跑完后用 state.decisions 校验是否按 StateGraph 里程碑走通",
)
@click.option(
    "--verify-json/--no-verify-json",
    default=False,
    help="校验报告以 JSON 输出(默认人类可读)",
)
@click.option(
    "--no-interrupt",
    is_flag=True,
    help="无人值守跑完全图(等价 ATELIER_INTERRUPT_DEFAULT=false)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="只跑状态机拓扑,不调 LLM / 不写文件(测试用)",
)
@click.option(
    "--stream/--no-stream",
    default=True,
    help="流式打印每个 StateGraph 节点完成进度(stderr,默认开)",
)
@click.option("--quiet", is_flag=True, help="关闭 stderr 进度输出")
def run(
    plan_path: str,
    thread: str | None,
    workdir: str | None,
    verify: bool,
    verify_json: bool,
    no_interrupt: bool,
    dry_run: bool,
    stream: bool,
    quiet: bool,
) -> None:
    """Run a plan.md end-to-end through the compound-builder graph."""
    if quiet:
        os.environ["ATELIER_QUIET"] = "true"
    if dry_run:
        os.environ["ATELIER_DRY_RUN"] = "true"
    else:
        os.environ["ATELIER_DRY_RUN"] = "false"
    if no_interrupt:
        os.environ["ATELIER_INTERRUPT_DEFAULT"] = "false"
    if _dotenv_used:
        click.echo(f"[cli] loaded env from {_dotenv_used}", err=True)
    else:
        base = os.getenv("ANTHROPIC_BASE_URL", "(default anthropic)")
        model = resolve_default_model()
        click.echo(f"[cli] model={model!r} base_url={base}", err=True)

    wd = _resolve_workdir(workdir)
    tracing.init_tracing(project=os.getenv("LANGSMITH_PROJECT", "atelier-compound_builder"))
    plan_file = Path(plan_path).resolve()
    graph = build_agent()

    state = {
        "plan": {},
        "units": [],
        "fix_units": [],
        "current_unit_index": 0,
        "phase": "init",
        "review_findings": [],
        "fix_plan_path": None,
        "review_round": 0,
        "repair_budget_used": 0,
        "decisions": [],
        "last_error": None,
        "messages": [],
        "results_log": [],
        "workdir": str(wd),
        "plan_path": str(plan_file),
    }

    thread_id = thread or str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    progress(f"thread_id={thread_id} plan={plan_file}")
    result = _invoke_graph(graph, state, cfg, stream=stream)

    n_units = len(result.get("units") or (result.get("plan") or {}).get("units") or [])

    payload = {
        "thread_id": thread_id,
        "workdir": str(wd),
        "phase": result.get("phase"),
        "final_report": result.get("final_report"),
        "review_report_path": result.get("review_report_path"),
        "fix_plan_path": result.get("fix_plan_path"),
        "decisions_tail": (result.get("decisions") or [])[-20:],
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    review_doc = result.get("review_report_path")
    final_doc = (result.get("final_report") or {}).get("final_report_path")
    if review_doc:
        progress(f"review report: {review_doc}")
    if final_doc:
        progress(f"final report: {final_doc}")

    if verify:
        report = verify_flow(result, expect="happy", n_units=n_units)
        _echo_verify(report, as_json=verify_json)
        if not report.ok:
            raise SystemExit(1)


@cli.command()
@click.argument("thread_id")
def replay(thread_id: str) -> None:
    """Replay all states of a thread."""
    load_cli_env(override=True)
    graph = build_agent()
    cfg = {"configurable": {"thread_id": thread_id}}
    for state in graph.get_state_history(cfg):
        click.echo(
            f"[{state.created_at}] next={state.next} "
            f"phase={state.values.get('phase')} "
            f"keys={list(state.values.keys())}"
        )


@cli.command()
@click.argument("thread_id")
@click.option(
    "--expect",
    type=click.Choice(["happy", "blocked", "any"], case_sensitive=False),
    default="happy",
    show_default=True,
    help="期望的流程形态",
)
@click.option("--json", "as_json", is_flag=True, help="JSON 输出校验报告")
def verify(thread_id: str, expect: str, as_json: bool) -> None:
    """从 checkpointer 回放 thread 并校验流程(无需手传 log)。"""
    load_cli_env(override=True)
    graph = build_agent()
    cfg = {"configurable": {"thread_id": thread_id}}
    history = [s.values for s in graph.get_state_history(cfg)]
    if not history:
        click.echo(f"thread {thread_id!r}: no history", err=True)
        raise SystemExit(1)

    last = history[-1]
    n_units = len((last.get("plan") or {}).get("units") or last.get("units") or [])
    report = verify_flow(
        last,
        expect=expect,  # type: ignore[arg-type]
        n_units=n_units or None,
    )
    _echo_verify(report, as_json=as_json)
    if not report.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
