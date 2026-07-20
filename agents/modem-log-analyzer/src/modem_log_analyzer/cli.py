"""ModemLogAnalyzer 的命令行入口。

主入口:
    modem-log-analyzer analyze --evb-log <file> --output <dir> [选项]
    modem-log-analyzer --help

设计目标 (Plan §1, U3):
  - CLI 是首要交付入口。
  - ``analyze`` 默认走 **AI Agent** (``agent_runner.run_agent_analyze``)。
    确定性预处理 + Deep Agent 诊断 + schema 校验 + 确定性 renderer。
  - 旧 ``AnalysisService.run_analyze`` 降级为:
      1. dry-run 替身 (--dry-run 由 agent_runner 内部处理, 仍走 preprocess);
      2. 离线单测替身 (tests/integration 用 env ``MODEM_LOG_ANALYZER_RULES_BACKEND=1`` 启用);
      3. 严禁冒充主路径的 Agent 分析 (Plan S5)。
  - 必须从模块 import 之前完成 dotenv 加载与中间件 patch
    (避免 ``docs/solutions/integration-issues/code-writer-cli-502-compound-misconfig.md``
    记录的入口差异问题)。
  - ``analyze`` 不要求 loop 编号;control-log / label / thread / overwrite 全可选。
"""

from __future__ import annotations

import json
import os

import click

# 必须在任何业务 import 之前加载 .env 与 patch 中间件
from modem_log_analyzer.env import load_cli_env  # noqa: E402

_dotenv_used = load_cli_env(override=False)

# MiniMax 等 anthropic-compat 服务可能拒绝 cache_control → 502
# 与 code-writer/compound-builder 同样 patch
try:  # noqa: E402
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

    def _noop_wrap_model_call(self, request, handler):  # noqa: ANN001
        return handler(request)

    AnthropicPromptCachingMiddleware.wrap_model_call = _noop_wrap_model_call  # type: ignore[method-assign]
except Exception:  # pragma: no cover
    pass


# ============================================================
# 默认 runner: AI Agent (Plan U3 主路径)
# ============================================================
def _default_runner(
    *,
    evb_log_path: str,
    output_dir: str,
    control_log_path: str | None,
    label: str | None,
    thread_id: str | None,
    overwrite: bool,
    dry_run: bool,
) -> dict:
    """CLI 默认的诊断入口。

    Plan U3 主路径: AI Agent (``agent_runner.run_agent_analyze``)。
    Plan U5 降级: 在 ``MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1`` 时退回
    ``AnalysisService._run_rules_pipeline`` (用于离线单测、合成 e2e 等
    不依赖真实 LLM 的场景)。生产部署**不得**显式打开此开关。
    """
    if os.getenv("MODEM_LOG_ANALYZER_CLI_FORCE_RULES") == "1":
        from modem_log_analyzer.analysis_service import AnalysisService

        return AnalysisService()._run_rules_pipeline(
            evb_log_path=evb_log_path,
            output_dir=output_dir,
            control_log_path=control_log_path,
            label=label,
            thread_id=thread_id,
            overwrite=overwrite,
            dry_run=dry_run,
        )

    from modem_log_analyzer.agent_runner import run_agent_analyze

    return run_agent_analyze(
        evb_log_path=evb_log_path,
        output_dir=output_dir,
        control_log_path=control_log_path,
        label=label,
        thread_id=thread_id,
        overwrite=overwrite,
        dry_run=dry_run,
    )


# ============================================================
# CLI 入口
# ============================================================
@click.group()
@click.option(
    "--quiet",
    is_flag=True,
    help="关闭 stderr 进度输出",
)
def cli(quiet: bool) -> None:
    """Atelier ModemLogAnalyzer CLI.

    主入口: analyze (默认走 AI Agent)
    """
    if quiet:
        os.environ["MODEM_LOG_ANALYZER_QUIET"] = "true"


@cli.command()
@click.option(
    "--evb-log",
    "evb_log",
    required=True,
    type=click.Path(exists=False, dir_okay=False),
    help="单次 EVB 日志路径 (必需)",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(exists=False, file_okay=False),
    help="报告输出目录 (必需)",
)
@click.option(
    "--control-log",
    "control_log",
    default=None,
    type=click.Path(exists=False, dir_okay=False),
    help="可选: 同次执行的控制脚本日志路径",
)
@click.option("--label", default=None, help="可选: 自定义标识 (loop/case 等)")
@click.option("--thread", default=None, help="可选: LangGraph thread id")
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    help="允许覆盖已有 report.md / analysis.json (默认: 拒绝覆盖)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="仅做输入校验与预处理,不调用 LLM / 不写文件",
)
def analyze(
    evb_log: str,
    output_dir: str,
    control_log: str | None,
    label: str | None,
    thread: str | None,
    overwrite: bool,
    dry_run: bool,
) -> None:
    """Analyze a single NuttX EVB failure log via AI Agent.

    主路径: 确定性预处理 → Deep Agent 诊断 → schema 校验 → 确定性 renderer。
    ``--dry-run`` 跳过 LLM 调用与产物落盘, 仅返回预处理摘要。
    """
    if _dotenv_used and not os.getenv("MODEM_LOG_ANALYZER_QUIET"):
        click.echo(f"[cli] loaded env from {_dotenv_used}", err=True)

    if not os.getenv("MODEM_LOG_ANALYZER_QUIET"):
        from modem_log_analyzer.llm import resolve_default_model

        model = resolve_default_model()
        base = os.getenv("ANTHROPIC_BASE_URL", "(default anthropic)")
        click.echo(f"[cli] model={model!r} base_url={base}", err=True)

    if dry_run:
        click.echo("[cli] dry-run: skipping LLM, skipping file writes", err=True)

    # ---- intake (Agent 之前) ----
    from modem_log_analyzer.intake import (
        IntakeError,
        build_proxy_from_cli_kwargs,
        validate_run_request,
    )

    proxy = build_proxy_from_cli_kwargs(
        evb_log_path=evb_log,
        output_dir=output_dir,
        control_log_path=control_log,
        label=label,
        thread_id=thread,
        overwrite=overwrite,
        base_dir=os.getcwd(),
    )
    try:
        validated = validate_run_request(proxy)
    except IntakeError as e:
        click.echo(f"ERROR [{e.code}]: {e.message}", err=True)
        raise SystemExit(2) from e

    # ---- 委托给 AI Agent runner ----
    from modem_log_analyzer.report import (
        atomic_write_artifacts,
        render_terminal_summary,
    )

    try:
        result = _default_runner(
            evb_log_path=validated.evb_log_path,
            output_dir=validated.output_dir,
            control_log_path=validated.control_log_path,
            label=validated.label,
            thread_id=validated.thread_id,
            overwrite=validated.overwrite,
            dry_run=dry_run,
        )
    except (ValueError, FileNotFoundError, FileExistsError, NotImplementedError) as e:
        click.echo(f"ERROR: {e}", err=True)
        raise SystemExit(2) from e
    except RuntimeError as e:
        click.echo(f"ERROR [AGENT_INVOKE]: {e}", err=True)
        raise SystemExit(2) from e

    # ---- 写产物 (除非 dry_run) ----
    if not dry_run:
        try:
            atomic_write_artifacts(
                result=result,
                output_dir=validated.output_dir,
                overwrite=validated.overwrite,
            )
        except FileExistsError as e:
            click.echo(f"ERROR: {e}", err=True)
            raise SystemExit(2) from e
        except ValueError as e:
            click.echo(f"ERROR [INVALID_RESULT]: {e}", err=True)
            raise SystemExit(2) from e

        click.echo(
            f"[cli] report.md + analysis.json written to {validated.output_dir}",
            err=True,
        )

    # ---- 终端: 简洁摘要 + 完整 JSON ----
    click.echo(render_terminal_summary(result))
    click.echo("---")
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = ["cli", "_default_runner"]


if __name__ == "__main__":
    cli()