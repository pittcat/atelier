"""U3: CLI 默认接线 agent_runner (Fake runner)。

按 Plan Unit 3 / S1 / S2 / S3:
  - analyze 默认路径调用 ``agent_runner.run_agent_analyze`` 而非 AnalysisService。
  - ``--dry-run`` 不调 LLM、不写产物, 但能拿到预处理摘要。
  - 非法输入 (缺文件/冲突) 在 agent runner 之前失败, 0 次 runner 调用。
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


# ============================================================
# Test fixtures
# ============================================================
def _write_evb(tmp_path: Path, content: str) -> str:
    p = tmp_path / "evb.log"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _legal_draft(label: str = "loop75") -> dict:
    return {
        "schema_version": "0.1.0",
        "run_label": label,
        "classification": "DEVICE_FAILURE_CONFIRMED",
        "root_cause_confidence": "medium",
        "scenario": "语音通话 (Call)",
        "scenario_confidence": "high",
        "first_anomaly": None,
        "evidence_refs": [
            {
                "ref_id": "EV-0001",
                "source": "evb.log",
                "line_no": 1,
                "timestamp": "2026-07-19 10:00:00.000",
                "raw_text": "raw 1",
                "module": "ap",
            }
        ],
        "timeline": [],
        "root_cause_chain": [],
        "control_log_used": False,
        "external_result": "FAIL",
        "notes": [],
        "suggested_actions": [],
    }


# ============================================================
# Monkey-patched runner fixture
# ============================================================
class _FakeRunner:
    def __init__(self, draft):
        self._draft = draft
        self.calls: list[dict] = []

    def __call__(self, **_kwargs):
        self.calls.append(_kwargs)
        return self._draft


def _fake_runner_factory(draft):
    """Return a callable that records calls and returns draft."""
    r = _FakeRunner(draft)

    def _fn(**kwargs):
        r.calls.append(kwargs)
        return r._draft

    return r, _fn


# ============================================================
# S1 + S5 + S6: 默认 analyze 调用 Agent runner
# ============================================================
def test_cli_default_uses_agent_runner(tmp_path, monkeypatch):
    from modem_log_analyzer import cli as cli_mod

    fake, fake_fn = _fake_runner_factory(_legal_draft())
    # CLI 现在从 agent_runner.run_agent_analyze 取结果
    monkeypatch.setattr(cli_mod, "_default_runner", fake_fn)

    raw = (
        "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 0 14 13900000000\n"
        "[2026-07-19 10:00:01.000][apc1] OK\n"
        "[2026-07-19 10:00:05.000][apc1] ERROR: dial failed timeout\n"
    )
    log = _write_evb(tmp_path, raw)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stderr={result.stderr}"
    assert (out_dir / "report.md").exists()
    assert (out_dir / "analysis.json").exists()
    js = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert js["classification"] == "DEVICE_FAILURE_CONFIRMED"
    # runner 被调一次
    assert len(fake.calls) == 1


# ============================================================
# S3: 非法输入在 runner 之前失败
# ============================================================
def test_cli_invalid_input_does_not_invoke_runner(tmp_path, monkeypatch):
    from modem_log_analyzer import cli as cli_mod

    fake, fake_fn = _fake_runner_factory(_legal_draft())
    monkeypatch.setattr(cli_mod, "_default_runner", fake_fn)

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", "/no/such/file.log", "--output", str(tmp_path / "out")],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    # runner 必须 0 次调用
    assert len(fake.calls) == 0


def test_cli_output_conflict_does_not_invoke_runner(tmp_path, monkeypatch):
    from modem_log_analyzer import cli as cli_mod

    fake, fake_fn = _fake_runner_factory(_legal_draft())
    monkeypatch.setattr(cli_mod, "_default_runner", fake_fn)

    log = _write_evb(tmp_path, "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "report.md").write_text("old", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert len(fake.calls) == 0


# ============================================================
# S2: dry-run 不调 LLM, 不写产物
# ============================================================
def test_cli_dry_run_writes_nothing(tmp_path, monkeypatch):
    from modem_log_analyzer import cli as cli_mod

    fake, fake_fn = _fake_runner_factory(_legal_draft())
    monkeypatch.setattr(cli_mod, "_default_runner", fake_fn)

    log = _write_evb(tmp_path, "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n")
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", log, "--output", str(out_dir), "--dry-run"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # 不写文件
    assert not (out_dir / "report.md").exists()
    assert not (out_dir / "analysis.json").exists()
    # 但终端打印 JSON
    assert "classification" in result.stdout


# ============================================================
# S5: runner 抛错时, CLI 显式失败, 不静默回退规则
# ============================================================
def test_cli_runner_failure_surfaces_error(tmp_path, monkeypatch):
    from modem_log_analyzer import cli as cli_mod

    def _explode(**_):
        raise ValueError("INVALID: bad draft")

    monkeypatch.setattr(cli_mod, "_default_runner", _explode)

    log = _write_evb(tmp_path, "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n")
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert "INVALID" in result.stderr or "invalid" in result.stderr.lower()
    # 不应写半成品
    assert not (out_dir / "report.md").exists()
    assert not (out_dir / "analysis.json").exists()


# ============================================================
# 旧 AnalysisService 主路径不再被默认调用 (S16 / U5 降级)
# ============================================================
def test_cli_default_does_not_call_analysis_service_directly(tmp_path, monkeypatch):
    """CLI 必须显式不再把 AnalysisService 视作主路径。"""
    from modem_log_analyzer import cli as cli_mod
    from modem_log_analyzer import analysis_service as as_mod

    fake, fake_fn = _fake_runner_factory(_legal_draft())
    monkeypatch.setattr(cli_mod, "_default_runner", fake_fn)
    called = {"flag": False}

    def _no():
        called["flag"] = True
        return {"_": "stub"}

    monkeypatch.setattr(as_mod.AnalysisService, "run_analyze", _no)

    log = _write_evb(tmp_path, "[2026-07-19 10:00:00.000][ap] modemcli> !ifconfig\n")
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["analyze", "--evb-log", log, "--output", str(out_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert called["flag"] is False, "AnalysisService.run_analyze 不应被默认 CLI 调用"