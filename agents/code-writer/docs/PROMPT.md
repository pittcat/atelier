# Code Writer —— 提示词运维手册

> 真相之源。任何对 `src/code_writer/prompts.py` 的改动**必须**在这里追加一条变更记录。

## 主代理系统提示

> 见 `prompts.py:SYSTEM_PROMPT`

摘要：

- 角色：Code Writer
- 5 条 Operating Principles：先规划 / 先调研 / 小步验证 / 子代理 / 人工把关
- 4 条 Anti-patterns：refactor+behavior 一起 / 删测试 / 没跑 test log 就宣称完成 / 试图 push

## 子代理提示词

| Sub-agent | 主要行为 |
|-----------|----------|
| `researcher` | 只读；用 Read/Glob/Grep 调研；返回文件路径+行号 |
| `tester`     | 写并跑测试；末尾必须 `make format && make lint && make test` |
| `reviewer`   | 审 diff：correctness / edge case / perf / security / conventions |

## 变更记录

| 日期 | 版本 | 改动 | 原因 |
|------|------|------|------|
| 2026-07-04 | 0.1.0 | 初版（模板 + 示例混合） | atelier 平台搭建 |
| 2026-07-04 | 0.1.1 | `llm.py` 支持 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_CUSTOM_HEADER`（Anthropic 兼容三方如 Minimax 接入）；新增 `resolve_minimax_env()` 辅助 | 让 `llm.py` 默认就能切换三方 endpoint，不改业务代码 |

## 评测

- LangSmith Evaluator 接入方式（待补）
- 推荐数据集：每 Agent 至少 10 条真实任务 + 期望产出
