# CompoundBuilder Agent 宪法

> 本 Agent 自己的硬性约束。优先级低于仓库根 `AGENTS.md`，但可以加更严的要求。

## 不可违反

1. 永远不开 auto-push。
2. prompt / tool / subagent 改动必须同步 `docs/PROMPT.md`。
3. `bash`、`write_file`、`edit_file`、`git_commit` 必须配 interrupt_on。
4. 不允许引用其他 Agent（`from agents.<other> import ...` 会被 lint 拒收）。
5. 跨平台（macOS / Linux）路径必须用 `pathlib.Path`，禁止硬编码 `/` 或 `\\`。

## 改 PR 时

- 一个 PR = 一个语义改动；禁止混杂 refactor。
- 通过 `make format && make lint && make test` 才能提。
- 附注测试覆盖；写新功能必带测试。

## 沟通风格

- 用户用中文就中文回复，英文就英文。
- 终端输出 / 日志用英文（便于 grep）。
