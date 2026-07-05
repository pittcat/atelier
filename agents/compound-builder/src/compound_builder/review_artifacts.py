"""Review 产物落盘 —— findings / 审核报告 / fix-plan。"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from compound_builder.state import Finding, Plan, Unit


def review_round_dir(workdir: str | Path, round_no: int) -> Path:
    d = Path(workdir) / ".compound_builder" / "review_rounds" / f"r{round_no:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_findings_json(
    workdir: str | Path,
    round_no: int,
    findings: list[Finding],
) -> Path:
    out = review_round_dir(workdir, round_no) / "review-findings.json"
    out.write_text(
        json.dumps([dict(f) for f in findings], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def write_fix_plan_json(
    workdir: str | Path,
    round_no: int,
    findings: list[Finding],
) -> Path:
    out = review_round_dir(workdir, round_no) / "fix-plan.json"
    out.write_text(
        json.dumps([dict(f) for f in findings], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def _group_by_dimension(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        dim = str(f.get("dimension") or "unknown")
        grouped.setdefault(dim, []).append(f)
    return grouped


def write_review_report_md(
    workdir: str | Path,
    round_no: int,
    *,
    plan: Plan | None,
    units: list[Unit],
    findings: list[Finding],
    fix_plan_path: str | None,
) -> Path:
    """写人读的审核报告(每轮必有,即使 0 findings)。"""
    p0p1 = [f for f in findings if (f.get("severity") or "p3").lower() in {"p0", "p1"}]
    grouped = _group_by_dimension(findings)
    title = (plan or {}).get("title") or "(untitled plan)"
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Compound Builder Review Report — Round {round_no}",
        "",
        f"- **Generated:** {now}",
        f"- **Plan:** {title}",
        f"- **Units reviewed:** {len(units)}",
        f"- **Total findings:** {len(findings)}",
        f"- **Blocking (p0/p1):** {len(p0p1)}",
        "",
        "## Executive summary",
        "",
    ]
    if not findings:
        lines.append(
            "No issues recorded. All six dimensions returned clean within the "
            "reviewed diff scope."
        )
    elif p0p1:
        lines.append(
            f"**{len(p0p1)} blocking finding(s)** require fix-units before ship. "
            f"See fix-plan: `{fix_plan_path or 'fix-plan.json'}`."
        )
    else:
        lines.append(
            f"{len(findings)} non-blocking note(s) (p2/p3). Safe to ship without "
            "a fix-plan."
        )

    lines.extend(["", "## Acceptance criteria", ""])
    for item in (plan or {}).get("acceptance") or []:
        lines.append(f"- {item}")
    if not (plan or {}).get("acceptance"):
        lines.append("- (none in plan)")

    lines.extend(["", "## Implementation units", ""])
    for u in units:
        lines.append(
            f"- **{u.get('id')}** — {u.get('title')} "
            f"(`{u.get('status', 'unknown')}`)"
        )

    lines.extend(["", "## Findings by dimension", ""])
    if not grouped:
        lines.append("_No findings._")
    else:
        for dim in sorted(grouped):
            lines.append(f"### {dim}")
            lines.append("")
            for f in grouped[dim]:
                sev = (f.get("severity") or "p3").upper()
                loc = f.get("file") or "<unknown>"
                line_no = f.get("line")
                loc_str = f"{loc}:{line_no}" if line_no else loc
                lines.append(f"- **[{sev}]** `{loc_str}` — {f.get('summary', '')}")
                fix = f.get("suggested_fix")
                if fix:
                    lines.append(f"  - Suggested fix: {fix}")
            lines.append("")

    lines.extend(["", "## Fix plan", ""])
    if p0p1 and fix_plan_path and fix_plan_path != "null":
        lines.append(f"Blocking issues documented in: `{fix_plan_path}`")
        lines.append("")
        lines.append("| Severity | File | Summary |")
        lines.append("| -------- | ---- | ------- |")
        for f in p0p1:
            lines.append(
                f"| {(f.get('severity') or '').upper()} | {f.get('file', '')} "
                f"| {f.get('summary', '')} |"
            )
    else:
        lines.append("_No fix-plan required (no p0/p1 findings)._")

    out = review_round_dir(workdir, round_no) / "review-report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def paths_for_round(workdir: str | Path, round_no: int) -> dict[str, str]:
    base = review_round_dir(workdir, round_no)
    return {
        "review_report": str(base / "review-report.md"),
        "review_findings": str(base / "review-findings.json"),
        "fix_plan": str(base / "fix-plan.json"),
    }


__all__ = [
    "paths_for_round",
    "review_round_dir",
    "write_findings_json",
    "write_fix_plan_json",
    "write_review_report_md",
]
