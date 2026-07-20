"""End-to-end 验收: 跑 5 个 fixture (Call/SMS/Data-Ping/Setting/混合) 通过 CLI + Gateway。

fixtures 位于本仓库 ``tests/fixtures/e2e_cases/``,由 e2e 阶段构造:
  - case_call_failure        DEVICE_FAILURE_CONFIRMED
  - case_sms_failure         DEVICE_FAILURE_CONFIRMED
  - case_data_ping_failure   DEVICE_FAILURE_CONFIRMED
  - case_setting_success     NO_DEVICE_ANOMALY_FOUND
  - case_mixed_call_sms_ping TEST_AUTOMATION_FAILURE_CONFIRMED

跑法:
    cd atelier
    PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \\
      .venv/bin/python -m pytest agents/modem-log-analyzer/tests/e2e/test_end_to_end.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
FIXTURES_ROOT = REPO / "agents/modem-log-analyzer/tests/fixtures/e2e_cases"
PYTHONPATH = ":".join(
    [
        str(REPO / "agents/modem-log-analyzer/src"),
        str(REPO / "libs/common/src"),
    ]
)
PYTHON = REPO / ".venv/bin/python"


def _cases() -> list[Path]:
    if not FIXTURES_ROOT.exists():
        return []
    return sorted([p for p in FIXTURES_ROOT.iterdir() if p.is_dir()])


def _run_cli(fx: Path, out_dir: Path) -> tuple[int, dict | None]:
    args = [
        str(PYTHON),
        "-m",
        "modem_log_analyzer.cli",
        "analyze",
        "--evb-log",
        str(fx / "evb.log"),
        "--output",
        str(out_dir),
        "--label",
        fx.name,
    ]
    if (fx / "control.log").exists():
        args += ["--control-log", str(fx / "control.log")]
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    env["MODEM_LOG_ANALYZER_QUIET"] = "true"
    # Plan U5: 合成 e2e 用例依赖确定性规则管线, 不调真实 LLM
    env["MODEM_LOG_ANALYZER_CLI_FORCE_RULES"] = "1"
    # Plan U5: 让 FORCE_RULES 守卫放行 (合成 e2e 走非生产路径)
    env["ATELIER_ENV"] = "test"
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), env=env)
    if proc.returncode != 0:
        return proc.returncode, None
    aj = out_dir / "analysis.json"
    if not aj.exists():
        return 1, None
    return 0, json.loads(aj.read_text(encoding="utf-8"))


def _expected(fx: Path) -> dict:
    return json.loads((fx / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fx_name", [p.name for p in _cases()])
def test_cli_end_to_end(tmp_path: Path, fx_name: str):
    fx = FIXTURES_ROOT / fx_name
    if not (fx / "evb.log").exists():
        pytest.skip(f"fixture {fx_name} incomplete")
    expected = _expected(fx)
    rc, result = _run_cli(fx, tmp_path / "out")
    assert rc == 0, f"CLI 失败 rc={rc}"
    assert result is not None
    assert result["classification"] == expected["classification"], (
        f"{fx_name}: 分类不匹配 (期望 {expected['classification']}, "
        f"实际 {result['classification']})"
    )
    if "scenario_substring" in expected:
        assert expected["scenario_substring"].lower() in (result.get("scenario") or "").lower(), (
            f"{fx_name}: 场景名不含 {expected['scenario_substring']!r}"
        )
    # 产物存在
    assert (tmp_path / "out" / "report.md").exists()
    assert (tmp_path / "out" / "analysis.json").exists()
    # report.md 含章节标题
    md = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    for section in ["## 失败概览", "## 核心诊断", "## 正式证据索引"]:
        assert section in md, f"{fx_name}: report.md 缺 {section}"


@pytest.mark.parametrize("fx_name", [p.name for p in _cases()])
def test_gateway_end_to_end(fx_name: str):
    """Gateway 端到端: 上传 → invoke → (resume) → GET /report → DELETE。"""
    fx = FIXTURES_ROOT / fx_name
    if not (fx / "evb.log").exists():
        pytest.skip(f"fixture {fx_name} incomplete")
    expected = _expected(fx)

    # 重置 PYTHONPATH + 暂存目录
    import shutil

    staging = f"/tmp/e2e-pytest-{fx_name}"
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    os.environ["MODEM_LOG_ANALYZER_STAGING_DIR"] = staging
    # Plan U5: gateway 合成 e2e 用确定性规则管线, 不调真实 LLM
    os.environ["MODEM_LOG_ANALYZER_CLI_FORCE_RULES"] = "1"
    # Plan U5: 让 FORCE_RULES 守卫放行
    os.environ["ATELIER_ENV"] = "test"

    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "agents/modem-log-analyzer/src"))
    sys.path.insert(0, str(REPO / "libs/common/src"))
    sys.path.insert(0, str(REPO / "gateway/api"))

    import importlib

    import gateway.api.main as gateway_main

    importlib.reload(gateway_main)
    from fastapi.testclient import TestClient

    client = TestClient(gateway_main.app)
    thread_id = f"e2e-pytest-{fx_name}"

    # upload EVB
    evb = open(fx / "evb.log", "rb").read()
    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
        files={"artifact": ("evb.log", evb, "application/octet-stream")},
    )
    assert r.status_code == 200, f"upload evb 失败: {r.text}"
    evb_id = r.json()["artifact_id"]

    # invoke (no control)
    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs",
        json={"evb_artifact_id": evb_id, "label": fx_name},
    )
    assert r.status_code == 200, f"invoke 失败: {r.text}"
    final = r.json()

    # resume with control if present
    if (fx / "control.log").exists():
        ctrl = open(fx / "control.log", "rb").read()
        r = client.post(
            f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
            files={"artifact": ("control.log", ctrl, "application/octet-stream")},
        )
        assert r.status_code == 200
        ctrl_id = r.json()["artifact_id"]
        r = client.post(
            f"/agents/modem-log-analyzer/threads/{thread_id}/runs:resume",
            json={"control_artifact_id": ctrl_id, "evb_artifact_id": evb_id},
        )
        assert r.status_code == 200, f"resume 失败: {r.text}"
        final = r.json()

    # 校验分类
    assert final["classification"] == expected["classification"], (
        f"{fx_name}: gateway 分类 (期望 {expected['classification']}, "
        f"实际 {final['classification']})"
    )

    # 路径穿越防护
    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs:resume",
        json={"control_artifact_id": "../../../etc/passwd"},
    )
    assert r.status_code == 400, f"路径穿越防护失效: {r.status_code}"

    # GET /report
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/report")
    assert r.status_code == 200, f"GET /report 失败: {r.status_code}"
    assert "## 失败概览" in r.json()["report_md"]

    # DELETE 清理
    r = client.delete(f"/agents/modem-log-analyzer/threads/{thread_id}")
    assert r.status_code == 200

    # 清理后 report 应 404
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/report")
    assert r.status_code == 404
