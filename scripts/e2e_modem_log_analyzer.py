#!/usr/bin/env python3
"""E2E 测试: 用 5 个 fixture 跑 CLI 主路径 + Gateway 完整链路。

fixtures 位于 /tmp/e2e_fixtures/,由执行脚本创建:
  - case_call_failure        (debug_bes_rpc 1 + 板端 ERROR → DEVICE_FAILURE_CONFIRMED)
  - case_sms_failure         (debug_bes_rpc 3 + 板端 ERROR → DEVICE_FAILURE_CONFIRMED)
  - case_data_ping_failure   (!ping + TIMEOUT → DEVICE_FAILURE_CONFIRMED)
  - case_setting_success     (!ifconfig OK → NO_DEVICE_ANOMALY_FOUND)
  - case_mixed_call_sms_ping (混合 + 控制侧 AssertionError → TEST_AUTOMATION_FAILURE_CONFIRMED)

退出码 0 = 全部通过; 1 = 有失败。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path("/Users/pittcat/Dev/Python/atelier")
FIXTURES_ROOT = REPO / "agents/modem-log-analyzer/tests/fixtures/e2e_cases"
PYTHONPATH = ":".join([
    str(REPO / "agents/modem-log-analyzer/src"),
    str(REPO / "libs/common/src"),
])
PYTHON = REPO / ".venv/bin/python"


def run_cli(fx_dir: Path, out_dir: Path) -> tuple[int, dict | None]:
    """跑 CLI 主路径;返回 (exit_code, analysis.json dict or None)。"""
    args = [
        str(PYTHON), "-m", "modem_log_analyzer.cli", "analyze",
        "--evb-log", str(fx_dir / "evb.log"),
        "--output", str(out_dir),
        "--label", fx_dir.name,
    ]
    if (fx_dir / "control.log").exists():
        args += ["--control-log", str(fx_dir / "control.log")]
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    env["MODEM_LOG_ANALYZER_QUIET"] = "true"
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), env=env)
    if proc.returncode != 0:
        return proc.returncode, None
    # analysis.json 存在?
    aj = out_dir / "analysis.json"
    if not aj.exists():
        return 1, None
    return 0, json.loads(aj.read_text(encoding="utf-8"))


def check_case(fx_dir: Path) -> tuple[bool, str]:
    """对单个 fixture 跑 CLI + 校验分类。"""
    expected = json.loads((fx_dir / "expected.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td) / "out"
        rc, result = run_cli(fx_dir, out_dir)
        if rc != 0 or result is None:
            return False, f"CLI 失败 rc={rc}"

    cls = result["classification"]
    if cls != expected["classification"]:
        return False, f"分类不匹配: 期望 {expected['classification']}, 实际 {cls}"

    if "scenario_substring" in expected:
        scenario = (result.get("scenario") or "").lower()
        if expected["scenario_substring"].lower() not in scenario:
            return False, f"场景名不含 {expected['scenario_substring']!r}: {scenario!r}"

    return True, f"cls={cls} scenario={result.get('scenario')}"


def check_gateway(fx_dir: Path) -> tuple[bool, str]:
    """通过 Gateway 完整跑一遍。"""
    # 必须确保 gateway 在 sys.path 顶层, 因为 TestClient import gateway.api.main
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "agents/modem-log-analyzer/src"))
    sys.path.insert(0, str(REPO / "libs/common/src"))

    os.environ["MODEM_LOG_ANALYZER_STAGING_DIR"] = f"/tmp/e2e-modem-la-{fx_dir.name}"

    import importlib
    import gateway.api.main as gateway_main
    importlib.reload(gateway_main)
    from fastapi.testclient import TestClient

    client = TestClient(gateway_main.app)
    thread_id = f"e2e-{fx_dir.name}"

    evb = open(fx_dir / "evb.log", "rb").read()
    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
        files={"artifact": ("evb.log", evb, "application/octet-stream")},
    )
    if r.status_code != 200:
        return False, f"upload evb 失败: {r.status_code}"
    evb_id = r.json()["artifact_id"]

    r = client.post(
        f"/agents/modem-log-analyzer/threads/{thread_id}/runs",
        json={"evb_artifact_id": evb_id, "label": fx_dir.name},
    )
    if r.status_code != 200:
        return False, f"invoke 失败: {r.status_code} {r.text}"
    invoke_summary = r.json()

    ctrl_id = None
    if (fx_dir / "control.log").exists():
        ctrl = open(fx_dir / "control.log", "rb").read()
        r = client.post(
            f"/agents/modem-log-analyzer/threads/{thread_id}/artifacts",
            files={"artifact": ("control.log", ctrl, "application/octet-stream")},
        )
        ctrl_id = r.json()["artifact_id"]
        r = client.post(
            f"/agents/modem-log-analyzer/threads/{thread_id}/runs:resume",
            json={"control_artifact_id": ctrl_id, "evb_artifact_id": evb_id},
        )
        if r.status_code != 200:
            return False, f"resume 失败: {r.status_code} {r.text}"
        final_summary = r.json()
    else:
        final_summary = invoke_summary

    # 校验分类
    expected = json.loads((fx_dir / "expected.json").read_text(encoding="utf-8"))
    if final_summary["classification"] != expected["classification"]:
        return False, (
            f"gateway 分类不匹配: 期望 {expected['classification']}, "
            f"实际 {final_summary['classification']}"
        )

    # GET /report 应有内容
    r = client.get(f"/agents/modem-log-analyzer/threads/{thread_id}/report")
    if r.status_code != 200:
        return False, f"GET /report 失败: {r.status_code}"
    if "## 失败概览" not in r.json()["report_md"]:
        return False, "report.md 缺 ## 失败概览"

    # DELETE 清理
    r = client.delete(f"/agents/modem-log-analyzer/threads/{thread_id}")
    if r.status_code != 200:
        return False, f"DELETE 失败: {r.status_code}"

    return True, (
        f"gateway 端到端 OK; cls={final_summary['classification']}; "
        f"evidence_ref_count={final_summary['evidence_ref_count']}"
    )


def main() -> int:
    if not FIXTURES_ROOT.exists():
        print(f"FAIL: fixtures 目录不存在 {FIXTURES_ROOT}", file=sys.stderr)
        return 1

    cases = sorted([p for p in FIXTURES_ROOT.iterdir() if p.is_dir()])
    if not cases:
        print("FAIL: 没有 fixture 目录", file=sys.stderr)
        return 1

    print("=" * 70)
    print(f"  E2E: {len(cases)} cases")
    print("=" * 70)

    all_passed = True
    for fx in cases:
        print(f"\n--- {fx.name} ---")
        ok1, msg1 = check_case(fx)
        print(f"  [CLI]     {'PASS' if ok1 else 'FAIL'}: {msg1}")
        ok2, msg2 = check_gateway(fx)
        print(f"  [Gateway] {'PASS' if ok2 else 'FAIL'}: {msg2}")
        if not (ok1 and ok2):
            all_passed = False

    print("\n" + "=" * 70)
    print(f"  {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print("=" * 70)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())