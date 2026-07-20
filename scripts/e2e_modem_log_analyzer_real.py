#!/usr/bin/env python3
"""Real-data E2E: run modem-log-analyzer CLI on the AutoCase-modem-52 sample.

Sample dir:
  agents/modem-log-analyzer/tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/

Plan §5 U6:
  - 真实调用 ``agent_runner.run_agent_analyze`` (CLI 默认主路径)。
  - 有 LLM key 时 exit 0 + report.md + analysis.json schema 合法。
  - 无 key 时**显式 skip** (exit 78 / 退出码 0 + stderr WARN), 绝不静默退化为
    规则管线冒充 Agent 诊断。

Exit 0  = CLI succeeded and wrote report.md + analysis.json.
Exit 78 = skipped (no LLM key available).
Exit 1+ = CLI or artifact failed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE = (
    REPO
    / "agents/modem-log-analyzer/tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75"
)
OUT = Path("/tmp/modem-la-real-52")
PYTHONPATH = ":".join(
    [
        str(REPO / "agents/modem-log-analyzer/src"),
        str(REPO / "libs/common/src"),
    ]
)
PYTHON = (
    REPO
    / "agents/modem-log-analyzer/.venv/bin/python"
    if (REPO / "agents/modem-log-analyzer/.venv/bin/python").exists()
    else REPO / ".venv/bin/python"
)


def _has_llm_key() -> bool:
    """Plan U6: 没有真实 LLM key 不可静默 PASS。

    接受 ``ANTHROPIC_AUTH_TOKEN`` / ``ANTHROPIC_API_KEY`` 中任一非空、非 ``test-no-key``。
    """
    for env_var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        v = os.getenv(env_var, "").strip()
        if v and v != "test-no-key":
            return True
    return False


def main() -> int:
    if not (SAMPLE / "merge.log").is_file():
        print(f"FAIL: missing {SAMPLE / 'merge.log'}", file=sys.stderr)
        return 1
    if not (SAMPLE / "control_script.log").is_file():
        print(f"FAIL: missing {SAMPLE / 'control_script.log'}", file=sys.stderr)
        return 1
    if not (SAMPLE / "modemcli_commands.md").is_file():
        print(f"FAIL: missing {SAMPLE / 'modemcli_commands.md'}", file=sys.stderr)
        return 1

    if not _has_llm_key():
        print("=" * 70, file=sys.stderr)
        print("  SKIP: no LLM key detected (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN)", file=sys.stderr)
        print("        Real-sample Agent E2E requires a working MiniMax / Anthropic key.", file=sys.stderr)
        print("        Set the env var and rerun, OR run tests/e2e/test_end_to_end.py", file=sys.stderr)
        print("        with MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1 for the synthetic path.", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return 78  # pytest convention for skip

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    env.pop("MODEM_LOG_ANALYZER_QUIET", None)

    args = [
        str(PYTHON),
        "-m",
        "modem_log_analyzer.cli",
        "analyze",
        "--evb-log",
        str(SAMPLE / "merge.log"),
        "--control-log",
        str(SAMPLE / "control_script.log"),
        "--output",
        str(OUT),
        "--label",
        "auto_case_modem_52_loop75",
        "--overwrite",
    ]
    print("=" * 70)
    print("  REAL E2E (Plan U6): auto_case_modem_52 loop75")
    print("  主路径: agent_runner.run_agent_analyze (CLI 默认)")
    print(f"  EVB:     {SAMPLE / 'merge.log'}")
    print(f"  Control: {SAMPLE / 'control_script.log'}")
    print(f"  Catalog: {SAMPLE / 'modemcli_commands.md'}")
    print(f"  Output:  {OUT}")
    print("=" * 70)

    proc = subprocess.run(args, cwd=str(REPO), env=env, text=True)
    if proc.returncode != 0:
        print(f"FAIL: CLI exit {proc.returncode}", file=sys.stderr)
        return proc.returncode

    report = OUT / "report.md"
    analysis = OUT / "analysis.json"
    if not report.is_file() or not analysis.is_file():
        print("FAIL: missing report.md or analysis.json", file=sys.stderr)
        return 1

    data = json.loads(analysis.read_text(encoding="utf-8"))
    print("\n--- RESULT ---")
    print(f"classification: {data.get('classification')}")
    print(f"scenario:       {data.get('scenario')}")
    print(f"confidence:     {data.get('root_cause_confidence')}")
    print(f"control_used:   {data.get('control_log_used')}")
    print(f"evidence_refs:  {len(data.get('evidence_refs') or [])}")
    print(f"report.md:      {report}")
    print(f"analysis.json:  {analysis}")

    # Plan U6: 关键结论分类必须 ∈ 6 枚举 (AnalysisResult schema 已硬约束)
    allowed = {
        "DEVICE_FAILURE_CONFIRMED",
        "ENVIRONMENT_FAILURE_INDICATED",
        "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "NO_DEVICE_ANOMALY_FOUND",
        "DEVICE_EVIDENCE_INCOMPLETE",
        "MULTIPLE_POSSIBLE_CAUSES",
    }
    cls = data.get("classification")
    if cls not in allowed:
        print(f"FAIL: classification {cls!r} 不在 6 枚举中", file=sys.stderr)
        return 1
    if not (data.get("evidence_refs") or []):
        print("FAIL: 0 个 evidence_refs, Agent 未产出真实引用", file=sys.stderr)
        return 1

    print("\nPASS (real Agent path)")
    print(f"Open report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
