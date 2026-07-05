# Compound Builder — e2e 验收 Runbook

> 用途:每次 Compound Builder 大版本升级时,按本 runbook 回放 Phase 4 / U9 的
> e2e 验证流程,确认新版本仍能"plan.md 进 → graph 走完 → terminal phase"。

## 0. 前置条件

| 项 | 值 |
|----|----|
| 工作目录 | `agents/compound-builder/` |
| Python | `uv sync` 通过 |
| LLM 可选 | 真实 LLM 接入需要 `ANTHROPIC_API_KEY`;骨架验证可无 |
| LangSmith 可选 | 真实 trace 需要 `LANGSMITH_API_KEY` |

## 1. 快速 smoke 回放(无 LLM)

```bash
cd agents/compound-builder
uv sync
uv run pytest tests/integration -q          # 状态机验证
uv run pytest tests/unit -q                # tools/phase_authority/repair_budget
```

期望:全部通过(20+ tests)。

## 2. 骨架层 e2e(graph-only)

不调真实 LLM,只验证 graph 在 stub 输入下能完成 happy path:

```bash
cd agents/compound-builder
uv run python <<'PY'
import uuid
from compound_builder.agent import build_agent

agent = build_agent()
state = {
    "plan": {"title": "trivial", "acceptance": [], "scope_boundaries": [], "units": [
        {"id": "step-01", "title": "add README section",
         "files": [], "approach": "", "test_scenarios": [],
         "verification": "make test"},
    ]},
    "units": [{
        "id": "step-01", "title": "add README section",
        "files": [], "approach": "", "test_scenarios": [],
        "verification": "make test",
        "status": "pending", "task_id": None, "attempt_count": 0,
        "last_error": None, "is_fix_unit": False,
    }],
    "fix_units": [], "current_unit_index": 0, "phase": "unit_loop",
    "review_findings": [], "fix_plan_path": None, "review_round": 0,
    "repair_budget_used": 0, "decisions": [], "last_error": None,
    "messages": [], "results_log": [],
}
cfg = {"configurable": {"thread_id": f"r-{uuid.uuid4()}", "recursion_limit": 25}}
out = agent.invoke(state, config=cfg)
assert out["phase"] == "terminal", out["phase"]
assert out["final_report"]["verdict"] == "pass"
print("OK phase=terminal verdict=pass")
PY
```

期望:输出 `OK phase=terminal verdict=pass`(实测数十毫秒)。

## 3. CLI 调用回放

```bash
cd agents/compound-builder
uv run python -m compound_builder.cli --help   # 仅冒烟
```

如果 `cli run --plan ...` 命令卡住(60s+ 无输出),**已知 issue**:CLI 子进程路径下
`build_agent()` 可能在 plan 文件读取时挂。fallback 用 Python 调用 `agent.invoke(...)`
(参 step 2)代替。

## 4. 真实 LLM e2e(待 ANTHROPIC_API_KEY 接入后)

```bash
cd /Users/pittcat/Dev/Rust/ralph-e2e
python reset_sort.py                            # 回到 "chore: initial" 那个 commit
cd -                                            # 回 compound-builder
ANTHROPIC_API_KEY=...  python -m compound_builder.cli run \
  --plan /Users/pittcat/Dev/Rust/ralph-e2e/sorts/docs/plans/python-sort-algorithms.md \
  --workdir /Users/pittcat/Dev/Rust/ralph-e2e
```

预期:`phase=terminal` + `verdict=pass` + ralph-e2e 工作目录中**没有**任何
`git push` 痕迹(`rg "git push" .compound_builder_review_run/` 0 命中)。

## 5. 失败模式

| 现象 | 可能原因 |
|------|---------|
| `graph.invoke` 进入死循环 | fixture verification 缺;dimension_reviewer 写 p1 → synth 写 fix_units → loop |
| `InvalidUpdateError on review_findings` | state.py 未声明 `Annotated[list, operator.add]` |
| `Phase never reaches terminal` | coordinator review-branch condition 漏 fix_plan 路径 |
| `tools.py 含 git_push` | smoke.sh 段 9 fail;检查 `_assert_no_push` |

## 6. 产物归档

每次大版本升级跑完后落:

- `ops/logs/<date>-compound-builder-e2e/run-trace.jsonl`
- `ops/logs/<date>-compound-builder-e2e/commits.log`
- `ops/logs/<date>-compound-builder-e2e/finding-diffs/<dim>.json`
- `ops/logs/<date>-compound-builder-e2e/final-report.md`
- `docs/solutions/e2e-compound-builder-<date>.md`(incident write-up)

## 7. 升级到 v0.2 的清单(下次 PR 范围)

- [ ] executor / fixer / dimension_reviewer 节点接入 LangChain ChatModel
- [ ] interrupt_on 真实挂到 bash / write_file / edit_file / git_commit 工具调用
- [ ] ralph-e2e 真 e2e + trace 上传 LangSmith
- [ ] CLI 卡死 root-cause 调查
- [ ] plan.md fixture 默认值(`verification: make test`)自动补齐
