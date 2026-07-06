# Compound Builder — 提示词运维手册

> 这是该 Agent 的 prompt 真相之源。任何对 `src/compound_builder/prompts.py`
> 的改动 **必须** 在本文件追加变更记录(AGENTS.md 规则 #3)。

## 节点 prompt 索引

每个 StateGraph 节点的 prompt 在 `prompts.py` 里有独立常量(`SYSTEM_PROMPT_<NODE>`):

| Node constant                  | 节点函数                              | 说明                                       |
| ------------------------------ | ------------------------------------- | ------------------------------------------ |
| `SYSTEM_PROMPT_COORDINATOR`    | `nodes.coordinator.coordinator`       | phase 路由(确定性)                           |
| `SYSTEM_PROMPT_COORDINATOR_PARSE` | `coordinator_plan._parse_llm`   | **init**: LLM 读 plan.md → units           |
| `SYSTEM_PROMPT_EXECUTOR`       | `nodes.executor.executor`             | 每 unit 的 TDD 任务分发                    |
| `SYSTEM_PROMPT_VALIDATOR`      | `validator_agent.run_validator_agent` | **Validator Agent**(ReAct):读仓库 + 跑全量套件;pass/fail 看 exit code |
| `SYSTEM_PROMPT_FIXER`          | `nodes.fixer.fixer`                   | 受 `repair_budget` 约束的修复              |
| `SYSTEM_PROMPT_REVIEW_COORDINATOR` | `nodes.review_coordinator.review_coordinator` | Send(map) 6 维 fan-out 调度              |
| `SYSTEM_PROMPT_DIMENSION_REVIEWER` | `reviewer_agent.run_dimension_review_agent` | **Reviewer Agent**:只读探索 ReAct → structured findings |
| `SYSTEM_PROMPT_REVIEWER_EXPLORATION` | `reviewer_agent.run_exploration_phase` | 探索阶段:读 patch/源文件,产出 audit memo |
| `SYSTEM_PROMPT_REVIEWER_STRUCTURED` | `reviewer_agent.run_structured_finalize` | 结构化收尾(带校验错误重试) → `review_synthesizer` |
| `SYSTEM_PROMPT_REVIEW_SYNTHESIZER` | `nodes.review_synthesizer.review_synthesizer` | Join + **落盘** review-report / fix-plan |
| `SYSTEM_PROMPT_SHIPPER`        | `nodes.shipper.shipper`               | 终态 gate:全部 passed 才 phase=plan_end   |
| `SYSTEM_PROMPT_REPORTER`       | `nodes.reporter.reporter`             | 写 `state.final_report` + phase=terminal  |
| `SYSTEM_PROMPT_PROGRESS_STEWARD` | `nodes.progress_steward.progress_steward` | 占位 log tap 节点,返回 `{}`              |

> **重要:** Executor / Fixer / Coordinator-init / **Validator Agent** 会调 LLM;其余节点多为确定性逻辑。
> Coordinator **init** 用 ``SYSTEM_PROMPT_COORDINATOR_PARSE`` + structured output;
> 路由阶段仍由 ``phase`` 字段 + 条件边保证不跳步(plan KTD-3)。

## 当前主代理提示

主图级别 prompt 见 `prompts.py:SYSTEM_PROMPT`(占位字符串,U4 阶段产出 per-node prompts 后作图级 fallback)。

## Skills 与 Ralph preset 的关系

| 资产 | 作用 |
| ---- | ---- |
| `skills/code-review-mindset/SKILL.md` | Atelier **通用** review 口吻(敌对、cite path:line、LGTM);注入 dimension reviewer,**不是**六维清单 |
| `prompts_dimensions.py` | 自 `ralph-orchestrator/.../ce-executor-serial.yml` 迁移的 **六维 checklist** |
| `skills/conventional-commit/SKILL.md` | commit message 规约;executor 通过 prompt 引用,非自动加载 |

## 与 code-writer 的差异

code-writer 使用传统 Deep Agents 大厨模式 + `task(...)` 委派。本 Agent 不再使用
sub_agent(`SUBAGENTS = []`),而是 10 个节点 + Send map,并通过 explicit
`phase` 字段而非"事件总线白名单"实现阶段权威(plan KTD-3)。

## 变更记录

| 日期       | 版本  | 改动                                                         | 原因                          |
| ---------- | ----- | ------------------------------------------------------------ | ----------------------------- |
| 2026-07-05 | 0.2.2 | Dimension reviewer 改为 ``reviewer_agent``:只读 ReAct 探索 + structured 收尾(校验失败带错误重试);``review_context`` 抽共享逻辑 | 大 patch 可读全;交卷 schema 不变,下一棒仍 synthesizer |
| 2026-07-05 | 0.2.1 | Validator 抽成独立 ``validator_agent``(ReAct);节点 ``nodes/validator`` 仅胶水;工具加 ``git_diff``/``git_status`` | Validator 必须是能读仓库的 Agent,不是外层 StateGraph 逻辑 |
| 2026-07-05 | 0.1.7 | Review finding `line` 自动解析 ``14-16`` / ``L14`` 等范围字符串 | 修复 adversarial structured output 校验失败 |
| 2026-07-05 | 0.1.4 | 每 unit 强制 commit(`git_ops`+Validator commit gate);`git_commit` 自动 `git add` | plan 要求 unit 级 commit + 全量回归 |
| 2026-07-05 | 0.1.3 | Dimension reviewer 接 LLM(`review_worker`);synthesizer 落盘 `review-report.md` + `fix-plan.json`;reporter 写 `final-report.json` | Review 不再是空壳,审核文档可交付 |
| 2026-07-05 | 0.1.2 | Validator 改为 LLM+tools 搜索并跑全量测试;pass/fail 仍看 exit code | 避免焊死 verification / discover 链 |
| 2026-07-05 | 0.1.1 | Coordinator init 接 LLM(`SYSTEM_PROMPT_COORDINATOR_PARSE`);CLI 不再前置 parse | 组织者应读 plan 拆 unit,非 stub |
| 2026-07-05 | 0.1.0 | 初版:从 cookiecutter 模板;每节点独立 `SYSTEM_PROMPT_<NODE>` | Phase 1 / U2 重写为 StateGraph |
| 2026-07-05 | 0.1.0 | Phase 3 / U4 补全 10 个节点 prompt + 索引表                 | AGENTS.md 规则 #3 落地         |

## 评测

跑 LangSmith Evaluator 的方式(后续 PR):

```bash
langsmith dataset create --name compound-builder-fixtures
langsmith dataset upload --name compound-builder-fixtures tests/eval/datasets/
```

`tests/eval/datasets/` 含 `plan-{tdd,refactor,characterization,trivial}.md` + `metadata.json`。
