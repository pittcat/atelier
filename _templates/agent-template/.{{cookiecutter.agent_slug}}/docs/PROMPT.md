# {{ cookiecutter.agent_pascal }} —— 提示词运维手册

> 这是该 Agent 的 prompt 真相之源。任何对 `src/{{ cookiecutter.agent_slug }}/prompts.py` 的改动
> **必须**在本文件追加变更记录。

## 当前主代理提示

> 见 `prompts.py:SYSTEM_PROMPT`

主提示词摘要：

- 角色：{{ cookiecutter.agent_display_name }}
- 使命：{{ cookiecutter.agent_description }}
- 5 条 Operating Principles：先规划 / 先探索 / 小步验证 / 子代理 / 人机协作 / 不推送。
- 7 条 Constraints：变更范围 / 依赖通知 / 不动数据。

## 子代理提示词

| Sub-agent | 提示词摘要 |
|-----------|-----------|
| `researcher` | 只读 / 用 Read+Glob+Grep 调研 |
| `tester`     | 写测试 + `make test`，失败必汇报 |
| `reviewer`   | 审 diff：correctness/perf/security |

## 变更记录

| 日期 | 版本 | 改动 | 原因 |
|------|------|------|------|
| {{ cookiecutter.agent_version }}  | 0.1.0 | 初版 | 模板生成 |

## 评测

跑 LangSmith Evaluator 的方式：

```bash
# 待补 docs/EVAL.md
```
