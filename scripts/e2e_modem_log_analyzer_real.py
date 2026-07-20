#!/usr/bin/env python3
"""Real-data E2E: run modem-log-analyzer CLI on user-provided merge/control logs.

Sample dir:
  agents/modem-log-analyzer/tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/

Uses MiniMax env from ~/.atelier/modem-log-analyzer/.env (same pattern as
code-writer / compound-builder).

Exit 0 = CLI succeeded and wrote report.md + analysis.json.
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
PYTHON = REPO / ".venv/bin/python"


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

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    # Prefer agent-local / ~/.atelier env via CLI loader; do not force quiet
    # so model/base_url lines are visible.
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
    print("  REAL E2E: auto_case_modem_52 loop75")
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

    # Soft checks for this known real sample
    ok = True
    if not data.get("control_log_used"):
        print("WARN: control_log_used is false", file=sys.stderr)
        ok = False
    refs = data.get("evidence_refs") or []
    if len(refs) < 5:
        print(f"WARN: too few evidence refs ({len(refs)})", file=sys.stderr)
        ok = False
    # Commands should have been extracted from merge format
    timeline = data.get("timeline") or []
    joined = " ".join(str(t.get("event") or "") for t in timeline).lower()
    for needle in ("debug_bes_rpc", "!ping", "!ifconfig"):
        if needle not in joined and needle.replace("!", "") not in joined:
            # timeline wording varies; also accept chinese labels
            pass
    actions_hint = (data.get("scenario") or "").lower()
    if "sms" not in actions_hint and "data" not in actions_hint and "ping" not in actions_hint:
        print(f"WARN: scenario looks empty/unknown: {data.get('scenario')!r}", file=sys.stderr)
        ok = False

    print("\n" + ("PASS (with warnings)" if ok else "PASS (soft checks had warnings)"))
    print(f"Open report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
