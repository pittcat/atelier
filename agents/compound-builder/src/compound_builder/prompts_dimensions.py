"""六维 review checklist —— 自 ralph ce-executor-serial dimension-reviewer 迁移。

来源: ``ralph-orchestrator/presets/en/ce-executor-serial.yml``
``dimension-reviewer.instructions`` WAVE_DIMENSION 块。
"""
from __future__ import annotations

DIMENSION_FOCUS: dict[str, str] = {
    "goal-alignment": (
        "Goal-to-plan-to-code alignment: core objective traceability, "
        "logical gaps, missing or divergent implementation steps"
    ),
    "correctness": (
        "Logic correctness, edge cases, error propagation, "
        "state machine consistency"
    ),
    "testing": (
        "Test coverage gaps, brittle assertions, "
        "behavioral changes without test additions"
    ),
    "maintainability": (
        "Coupling, complexity, naming, dead code, abstraction debt"
    ),
    "project-standards": (
        "AGENTS.md/CLAUDE.md compliance, frontmatter, citations, portability"
    ),
    "adversarial": (
        "Hidden side effects, compat breaks, edge/concurrency, unsafe paths, "
        "misleading names, test sufficiency, maintenance cost, rollback safety"
    ),
}

DIMENSION_CHECKLISTS: dict[str, str] = {
    "goal-alignment": """\
Principal Architect / TPM gate. Read-only — do NOT modify source.
Review whether the implementation achieves the stated core goal and whether
the plan and code have logical gaps. Do NOT flag generic bugs, memory leaks,
syntax errors, robustness, or security (other dimensions own those).

Check:
- **Core goal clarity**: plan defines a single verifiable objective.
- **Goal-to-plan traceability**: every plan section maps to the core goal.
- **Plan-to-code traceability**: major code steps correspond to plan items.
- **Logical continuity**: execution flow produces what the goal asks for.
- **Missing critical steps**: plan requires a step the code skips.
- **Scope creep / wrong direction**: code solves a different problem.

Severity:
- **p0** — Goal misalignment: output does not satisfy the core objective.
- **p1** — Significant plan deviation materially reducing intended outcome.
- **p2** — Secondary objective compromised while main goal is met.
- **p3** — Alignment suggestion; goal achieved but structure could be cleaner.

Every finding MUST tie back to core goal, plan, or execution flow.""",

    "correctness": """\
Check:
- **Off-by-one and boundary mistakes**: loop bounds, slices, pagination.
- **Null/undefined propagation**: nullable returns used without checks.
- **Race conditions and ordering**: shared state, async ordering, TOCTOU.
- **Incorrect state transitions**: invalid paths, flags not cleared on error.
- **Broken error propagation**: swallowed errors, masked failures.

Do NOT flag: style, missing optimizations, naming taste without evidence.""",

    "testing": """\
Check:
- **Untested branches**: new if/else/switch/try with no test.
- **Tests that don't assert behavior**: no-throw only, truthiness, heavy mocks.
- **Brittle implementation-coupled tests**: exact call counts, private methods.
- **Missing edge case coverage for error paths**.
- **Behavioral changes with no test additions**.

Do NOT flag: trivial getters, coverage percentages, unchanged code.""",

    "maintainability": """\
Read-only — do NOT modify source.

Check:
- **Coupling**: hidden cross-module dependencies, implicit ordering.
- **Complexity**: long/nested functions, cyclomatic spikes (cite file:line).
- **Naming**: identifiers that don't match behaviour (`get_*` mutates, etc.).
- **Dead code**: unused symbols, unreachable branches, debug prints left in.
- **Abstraction debt**: premature traits/wrappers with no real consumer.

Do NOT flag: pure style, missing doc comments, taste-only rewrites.""",

    "project-standards": """\
Read-only — do NOT modify source.

Check:
- **AGENTS.md / CLAUDE.md compliance**: new workflows reflected in agent docs.
- **Documentation frontmatter consistency**: status/plan_name drift vs siblings.
- **Citation integrity**: `file:line` references still point at claimed code.
- **Portability**: hard-coded absolute paths, machine-specific IDs in fixtures.
- **Secondary standards files** (STANDARDS.md, CONVENTIONS.md) if present.

Do NOT flag: style not in documented conventions; unverifiable claims.""",

    "adversarial": """\
Red-Team gate (last dimension). Read-only — treat findings as release-blockers
unless evidence shows the risk is contained.

Check:
- **Hidden side effects**: functions mutating beyond their name/implied contract.
- **Compatibility breaks**: public API, on-disk/wire format, runtime breakage.
- **Boundary and concurrency**: overflow, TOCTOU, locks across await/I/O, leaks.
- **Security paths**: injection, path traversal, secrets in logs/panics, authz bypass.
- **Misleading names**: `get_*` mutates, `is_*` does I/O, `*_safe` that isn't.
- **Test sufficiency**: no-throw-only tests, missing error-path tests, brittle mocks.
- **Maintenance cost and rollback safety**: magic numbers, new deps without payoff.

Do NOT flag: pure style, pre-existing issues outside this diff.
Unverified speculation: confidence low — do not block release alone.""",
}

__all__ = ["DIMENSION_FOCUS", "DIMENSION_CHECKLISTS"]
