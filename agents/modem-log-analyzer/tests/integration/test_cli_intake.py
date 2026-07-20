"""Unit 2 集成测试: CLI 非法输入在调用 runner 前失败, 合法请求正常委托。

约束 (Plan §3, Unit 2 + U3):
  - 测试使用 Fake ``_default_runner``, 记录被调用的次数与参数。
  - 非法输入必须使 CLI 返回非零退出码, stderr 含可操作错误, Fake 不被调用。
  - 合法输入 Fake runner 被恰好调用一次。
  - 本测试同进程运行 Click CLI (CliRunner.invoke), 这样 monkeypatch 可以生效。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeRunnerState:
    calls: list[dict] = []


def _install_fake_runner(monkeypatch: pytest.MonkeyPatch):
    """把 ``cli._default_runner`` 替换成计数 Fake。

    Plan U3 主路径默认走 _default_runner (= agent_runner.run_agent_analyze)。
    """
    from modem_log_analyzer import cli as cli_mod
    from modem_log_analyzer.cli import cli as cli_cmd

    def _fake_runner(**kwargs):
        _FakeRunnerState.calls.append(kwargs)
        return {
            "schema_version": "0.1.0",
            "run_label": kwargs.get("label") or "x",
            "classification": "DEVICE_FAILURE_CONFIRMED",
            "root_cause_confidence": "low",
            "evidence_refs": [],
            "timeline": [],
            "root_cause_chain": [],
            "control_log_used": False,
            "external_result": "FAIL",
            "notes": [],
            "suggested_actions": [],
            "first_anomaly": None,
            "_meta": {"dry_run": kwargs.get("dry_run", False)},
        }

    _FakeRunnerState.calls = []
    monkeypatch.setattr(cli_mod, "_default_runner", _fake_runner)
    _ = cli_cmd
    return _fake_runner


@pytest.fixture
def workspace(tmp_path):
    """提供: 合法 EVB 日志 / 合法输出目录。"""
    good_evb = tmp_path / "evb.log"
    good_evb.write_text("modemcli> debug_bes_rpc 1 0\nOK\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return {"evb": str(good_evb), "out": str(out_dir), "tmp": tmp_path}


def _invoke_cli(runner: CliRunner, *args: str):
    return runner.invoke(args, catch_exceptions=False)


# ============================================================
# 合法路径
# ============================================================


def test_legal_minimal_invokes_service(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["evb"], "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stderr={result.stderr} stdout={result.stdout}"
    assert len(_FakeRunnerState.calls) == 1
    call = _FakeRunnerState.calls[0]
    assert call["evb_log_path"] == workspace["evb"]
    assert call["output_dir"] == workspace["out"]


def test_legal_with_overwrite_invokes_service(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        [
            "analyze",
            "--evb-log",
            workspace["evb"],
            "--output",
            workspace["out"],
            "--overwrite",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(_FakeRunnerState.calls) == 1
    assert _FakeRunnerState.calls[0]["overwrite"] is True


def test_legal_with_label_invokes_service(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        [
            "analyze",
            "--evb-log",
            workspace["evb"],
            "--output",
            workspace["out"],
            "--label",
            "loop_52",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert _FakeRunnerState.calls[0]["label"] == "loop_52"


# ============================================================
# 非法路径 - 必须 fail-fast, Fake service 不被调用
# ============================================================


def test_missing_evb_log_fails_without_service(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    missing = str(workspace["tmp"] / "does_not_exist.log")
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", missing, "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert (
        "ERROR" in result.stderr
        or "not found" in result.stderr.lower()
        or "exists" in result.stderr.lower()
    )
    assert _FakeRunnerState.calls == [], "runner must not be called for missing evb-log"


def test_evb_log_is_a_directory_fails(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    # evb-log 指向 output_dir (它是目录), 期望 EVE_LOG_IS_DIR
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["out"], "--output", str(workspace["tmp"] / "out2")],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert _FakeRunnerState.calls == []


def test_empty_evb_log_fails(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    empty = workspace["tmp"] / "empty.log"
    empty.write_text("", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", str(empty), "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert _FakeRunnerState.calls == []


def test_unreadable_evb_log_fails(monkeypatch, workspace):
    import platform

    if platform.system() == "Windows":
        pytest.skip("POSIX permissions semantics")
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    unreadable = workspace["tmp"] / "no_read.log"
    unreadable.write_text("data", encoding="utf-8")
    unreadable.chmod(0o000)
    runner = CliRunner()
    try:
        result = runner.invoke(
            cli_cmd,
            ["analyze", "--evb-log", str(unreadable), "--output", workspace["out"]],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert _FakeRunnerState.calls == []
    finally:
        unreadable.chmod(0o644)


def test_output_dir_parent_unavailable_fails(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    bogus = str(workspace["tmp"] / "no_such_dir" / "out")
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["evb"], "--output", bogus],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert _FakeRunnerState.calls == []


def test_evb_log_path_validation_does_not_leak_content(monkeypatch, workspace):
    """错误信息不得泄露 EVB 日志内容。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    secret = "VERY_SECRET_PHONE_NUMBER_13900000000_AND_IMSI_460123456789012"
    sensitive = workspace["tmp"] / "sensitive.log"
    sensitive.write_text(secret, encoding="utf-8")
    runner = CliRunner()
    # output 父目录不存在 → 进入 OUT_PARENT_MISSING 路径
    result = runner.invoke(
        cli_cmd,
        [
            "analyze",
            "--evb-log",
            str(sensitive),
            "--output",
            str(workspace["tmp"] / "no_parent" / "out"),
        ],
        catch_exceptions=False,
    )
    combined = result.stderr + result.stdout
    assert secret not in combined, "sensitive content leaked into error message"


# ============================================================
# 覆盖保护 (S4)
# ============================================================


def test_existing_artifacts_blocked_by_default(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    (Path(workspace["out"]) / "report.md").write_text("old", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["evb"], "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert _FakeRunnerState.calls == [], "runner must not be called when overwrite blocked"
    assert (Path(workspace["out"]) / "report.md").read_text(encoding="utf-8") == "old"


def test_overwrite_flag_passes_through_to_service(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    (Path(workspace["out"]) / "report.md").write_text("old", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        [
            "analyze",
            "--evb-log",
            workspace["evb"],
            "--output",
            workspace["out"],
            "--overwrite",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(_FakeRunnerState.calls) == 1
    assert _FakeRunnerState.calls[0]["overwrite"] is True


# ============================================================
# CLI 不强制 loop 参数 (S2)
# ============================================================


def test_no_loop_flag_required(monkeypatch, workspace):
    """S2: analyze 命令必须允许在没有 --loop/--case 的情况下运行。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["evb"], "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert len(_FakeRunnerState.calls) == 1
    call = _FakeRunnerState.calls[0]
    assert "loop" not in call
    assert "case" not in call


def test_no_label_invokes_service_with_default_label(monkeypatch, workspace):
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        ["analyze", "--evb-log", workspace["evb"], "--output", workspace["out"]],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert _FakeRunnerState.calls[0]["label"] is None


def test_dry_run_does_not_require_overwrite_when_no_artifacts(monkeypatch, workspace):
    """dry-run 即使无 --overwrite 也合法(无产物保护)。"""
    from modem_log_analyzer.cli import cli as cli_cmd

    _install_fake_runner(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_cmd,
        [
            "analyze",
            "--evb-log",
            workspace["evb"],
            "--output",
            workspace["out"],
            "--dry-run",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert _FakeRunnerState.calls[0]["dry_run"] is True
