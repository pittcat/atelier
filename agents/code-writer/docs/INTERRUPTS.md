# Code Writer —— 触发中断的工具清单

按 `interrupt.py` 与 AGENTS.md 第三节：

| 工具 | 允许的人工决策 | 原因 |
|------|--------------|------|
| `bash`             | approve / edit / reject | shell 权限大、可执行任意命令 |
| `write_file`       | approve / reject       | 覆盖式写文件，可能破坏历史 |
| `edit_file`        | approve / reject       | 替换文本块 |
| `git_commit`       | approve / reject       | 提交影响未来 dev 流程 |
| `git_push`         | **不暴露**             | 永远人工，不在 Agent 工具集 |

## 审批 UI 建议

- 开发期：LangGraph Studio 自带中断弹窗
- 自建前端：通过 gateway/api 收到 `interrupt` 事件，前端自定义卡片（approve / 修改 args / reject）

## 调整规则

新增工具前确认：
1. 是否必须？（能用现有工具代替就别加）
2. 是否需要人工把关？（system 工具就别开）
3. 是否要在 `git` 系列里开 push？（开就要有审计日志）
