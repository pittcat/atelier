"""Unit 6 集成测试: CLI 完整 analyze 流程生成产物。

按 Plan §5 Unit 6:
  - 主路径: 给定合法 EVB 日志 → CLI 生成 report.md + analysis.json
  - 产物原子一致替换
  - dry-run 不写文件
  - interrupt 请求在 _meta 中可见
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _write_evb(tmp_path: Path, content: str) -> str:
    p = tmp_path / "evb.log"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_cli_analyze_full_path(tmp_path):
    """主路径: 失败 EVB → 生成 report.md + analysis.json。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed timeout\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stderr={result.stderr}"
    assert (out_dir / "report.md").exists()
    assert (out_dir / "analysis.json").exists()
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "## 失败概览" in md
    js = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert js["classification"] == "DEVICE_FAILURE_CONFIRMED"


def test_cli_analyze_dry_run_no_files(tmp_path):
    """dry-run 不写产物文件。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = "[2026-07-19 10:00:00.000][ap] modemcli> !ping 8.8.8.8\n"
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir), "--dry-run"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 不应有产物
    assert not (out_dir / "report.md").exists()
    assert not (out_dir / "analysis.json").exists()
    # 但终端应输出 JSON
    assert "classification" in result.stdout


def test_cli_analyze_clean_log_triggers_interrupt_metadata(tmp_path):
    """干净日志 → interrupt_request 在 _meta 中。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir), "--dry-run"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 解析 JSON 输出
    json_part = result.stdout.split("---")[1]
    parsed = json.loads(json_part)
    ir = parsed["_meta"].get("interrupt_request")
    assert ir is not None
    assert ir["type"] == "REQUEST_CONTROL_LOG"


def test_cli_analyze_overwrite_refuses(tmp_path):
    """已有产物 → 默认拒绝覆盖。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n[2026-07-19 10:00:01.000][apc1] eth0\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("old", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert (
        "ERROR" in result.stderr or "覆盖" in result.stderr or "overwrite" in result.stderr.lower()
    )
    # 旧产物应保留
    assert (out_dir / "report.md").read_text(encoding="utf-8") == "old"


def test_cli_analyze_overwrite_flag_writes(tmp_path):
    """--overwrite 允许覆盖。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n[2026-07-19 10:00:01.000][apc1] eth0\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("old", encoding="utf-8")
    (out_dir / "analysis.json").write_text("{}", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir), "--overwrite"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "## 失败概览" in md


def test_cli_terminal_summary_does_not_leak_phone(tmp_path):
    """终端摘要不应包含完整电话号码 (Plan §1 隐私)。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 1 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", log, "--output", str(out_dir), "--dry-run"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 终端摘要部分(--- 之前)不应包含完整电话号码
    summary_part = result.stdout.split("---")[0]
    assert "13900000000" not in summary_part
