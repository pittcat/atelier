"""ModemLogAnalyzer 的命令行入口。

主入口:
    modem-log-analyzer analyze --evb-log <file> --output <dir> [选项]
    modem-log-analyzer --help

设计目标 (Plan §1, Unit 1):
  - CLI 是首要交付入口。
  - 必须从模块 import 之前完成 dotenv 加载与中间件 patch
    (避免 ``docs/solutions/integration-issues/code-writer-cli-502-compound-misconfig.md``
    记录的入口差异问题)。
  - ``analyze`` 不要求 loop 编号;control-log / label / thread / overwrite 全可选。
  - Unit 1 阶段: ``analyze`` 仅做"输入校验 + 占位服务调用",输出明确的
    "尚未实现"退出码(2)。Unit 2+ 逐步接入 AnalysisService 与产物生成。

CLI dotenv 加载顺序:
  1. ``$ATELIER_HOME/.env``
  2. ``~/.atelier/modem-log-analyzer/.env``
  3. ``agents/modem-log-analyzer/.env`` (源码模式)
  4. 仓库根 ``.env`` (已安装倒推)
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

    主入口: analyze
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
    help="仅做输入校验,不调用 LLM / 不写文件",
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
    """Analyze a single NuttX EVB failure log and emit report.md + analysis.json."""
    if _dotenv_used and not os.getenv("MODEM_LOG_ANALYZER_QUIET"):
        click.echo(f"[cli] loaded env from {_dotenv_used}", err=True)

    if dry_run:
        click.echo("[cli] dry-run: skipping LLM, skipping file writes", err=True)

    # ---- Unit 2: 输入校验 (intake) ----
    # intake 在调用 service / Agent 之前拒绝所有非法输入。
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

    # ---- 委托给 AnalysisService ----
    from modem_log_analyzer.analysis_service import AnalysisService
    from modem_log_analyzer.report import (
        atomic_write_artifacts,
        render_terminal_summary,
    )

    service = AnalysisService()
    try:
        result = service.run_analyze(
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

    # ---- Unit 6: 写产物 (除非 dry_run) ----
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


if __name__ == "__main__":
    cli()
