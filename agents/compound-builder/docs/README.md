# Compound Builder

> Plan-driven multi-agent orchestrator. Runs a `plan.md` unit-by-unit through a
> TDD loop, then ships a reviewer panel verdict.

Compound Builder is a second Atelier agent shape — a **LangGraph StateGraph** —
designed for long, structured, parallelizable workflows where the Deep Agents
"chef" pattern can't reliably hold multi-stage state. Its first business scenario
is a 1:1 port of the Ralph `ce-executor-serial` workflow: every Implementation
Unit from `plan.md` gets its own TDD cycle, then 6 review dimensions run in
parallel, then a synthesizer routes through fix-units or straight to ship.

> Hard rules (inherited from `AGENTS.md`):
>
> 1. Never auto-push.
> 2. `prompts.py` changes must append to `docs/PROMPT.md`.
> 3. `bash` / `write_file` / `edit_file` / `git_commit` carry `interrupt_on=True`.
> 4. `MemorySaver` locally, `PostgresSaver` in production.
> 5. Plan worktree is owned by `gateway`, **never by this Agent**.

## Description

A plan-driven LangGraph agent with 10 nodes plus a 6-way `Send` fan-out:

```
START → coordinator ↔ executor ↔ validator ↔ fixer
                                       ↘
                                         (units exhausted)
                                            ↓
                                       review_coordinator
                                       (Send map → 6 dimensions)
                                            ↓
                                       review_synthesizer (Join)
                                            ↓
                                 coordinator (fix_plan = null → ship,
                                              fix_plan = path → fix_units)
                                            ↓
                                       shipper → reporter → END
```

Phase authority is held by `state.phase` — `coordinator` reads it, decides the
next hop, and writes it back. 6 reviewer dimensions are pulled from a static
list (`review_coordinator.DIMENSIONS`) and synthesized into either
`fix_plan_path = "null"` (ship) or a JSON fix-plan plus a derived list of
`fix_units`.

`repair_budget` defaults to `3` and is overridable via `ATELIER_REPAIR_BUDGET`.
Exceeding it routes to `phase=blocked` and `plan.blocked` is emitted.

## Installation

```bash
cd agents/compound-builder
uv sync
cp .env.example .env  # fill ANTHROPIC_API_KEY + LANGSMITH_API_KEY
```

Workspaces Python 3.11+. Requires the shared `atelier-common` library at
`../../libs/common`.

## Usage

### CLI

```bash
# run a plan.md
python -m compound_builder.cli run --plan ./tests/eval/datasets/plan-trivial.md

# replay a thread
python -m compound_builder.cli replay <thread_id>
```

### LangGraph Studio

```bash
make dev
# Studio at http://localhost:2024
```

### Gateway

`gateway/api/registry.py` registers `compound-builder` automatically once the
package is importable. Endpoints (mirroring `code_writer`):

```
POST   /agents/compound-builder/threads/{tid}/runs
POST   /agents/compound-builder/threads/{tid}/runs:stream
GET    /agents/compound-builder/threads/{tid}/state
GET    /agents/compound-builder/threads/{tid}/history
```

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `ANTHROPIC_API_KEY`     | (required)        | Default model + subagent model provider. |
| `ATELIER_DEFAULT_MODEL` | `claude-opus-4-8` | Coordinator / executor / validator / fixer / reviewer model. |
| `ATELIER_SUBAGENT_MODEL` | `claude-haiku-4-5-20251001` | Reserved (sub-agents not used by StateGraph mode). |
| `ATELIER_CHECKPOINTER_URL` | unset           | unset → `MemorySaver`; `postgresql://...` → `PostgresSaver.from_conn_string(...)` (与 code-writer / cookiecutter 模板同款约定,见 `checkpointer.py:18`). |
| `ATELIER_INTERRUPT_DEFAULT` | `true`        | `false` disables `interrupt_on` for `bash` / `write_file` / `edit_file` / `git_commit`. |
| `ATELIER_REPAIR_BUDGET` | `3`                | Single-unit retry budget before escalation to `plan.blocked`. |
| `LANGSMITH_PROJECT`     | `atelier-compound_builder` | Tracing project name. |
| `ATELIER_REVIEW_PARALLELISM` | `6` (env-only) | Concurrency cap for `Send(map)` reviewer fan-out. |

## State

```python
class CompoundBuilderState(TypedDict, total=False):
    plan: Plan                                # parsed plan.md
    units: list[Unit]                         # unit queue
    fix_units: list[Unit]                     # synthesized fix queue
    current_unit_index: int
    workdir: str
    phase: Phase                              # phase authority
    review_findings: list[Finding]            # 6-dim findings (merged)
    fix_plan_path: str | None                 # path OR literal "null"
    review_round: int
    repair_budget_used: int
    decisions: list[dict]
    last_error: str | None
    final_report: dict
```

Lists (`review_findings` / `decisions` / `messages` / `results_log`) use
`Annotated[list, operator.add]` so the 6-way `Send` parallel writes merge
correctly into one channel.

## Operations

### Smoke

```bash
make smoke   # at repo root: scripts/smoke.sh
```

Top-level layout tests assert presence of all 10 nodes + `compound_builder`
router registration.

### Tests

```bash
make test                          # all unit + integration
TEST=tests/integration make test   # just state-flow integration
```

20+ tests cover `parse_plan`, `discover_test_entry`, `phase_authority`,
`repair_budget`, `tools registry` (no push), and graph-level happy /
edge / error paths.

### Eval fixtures

`tests/eval/datasets/` ships four plan fixtures (TDD / refactor /
characterization / trivial) plus `metadata.json`. The LangSmith upload step is
out of scope for this PR (planned under follow-up work).

### Push policy

`tools.py` deliberately exports no `git_push` / `git_push_tool` /
`git_worktree_add`. `scripts/smoke.sh` section 9 greps for those identifiers to
catch regressions; the `_assert_no_push` runtime check fires if any code tries
to add one back.
