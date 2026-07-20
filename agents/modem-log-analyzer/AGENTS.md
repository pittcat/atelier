# ModemLogAnalyzer Agent 宪法

> 本 Agent 自己的硬性约束。优先级低于仓库根 `AGENTS.md`，但加严了"只读分析"的边界。

## 不可违反

1. 永远不开 auto-push。
2. prompt / tool / subagent 改动必须同步 `docs/PROMPT.md`。
3. **不暴露** `bash` / `write_file` / `edit_file` / `git_commit` / `git_push`（Plan §1 R16 + S16）。
   主代理与 subagent 工具集都不得注册这些。
4. 不允许引用其他 Agent（`from agents.<other> import ...` 会被 lint 拒收）。
5. 跨平台（macOS / Linux）路径必须用 `pathlib.Path`，禁止硬编码 `/` 或 `\\`。
6. **不读取用户级 / 全局 Skills / MCP**（AGENTS.md 硬规矩 8）。
7. **本 Agent 是只读日志分析器**：
   - 不读取整批压力测试目录，不自动切分 loop，不做跨 loop 聚类或失败率统计。
   - 不读取自动化测试源码。
   - 不自动操作 EVB，不执行 modem 命令，不复现测试。
   - 不进行外部 Web 搜索，不把未知芯片/协议栈/命令语义当成事实。

## 改 PR 时

- 一个 PR = 一个开发 Unit；禁止跨 Unit 混杂（Plan §5 串行门禁）。
- 通过 `make format && make lint && make test` 才能提。
- 附注测试覆盖；每个 Unit 必须有对应的 Red → Green → Refactor 闭环。

## 沟通风格

- 中文用户用中文回复（Plan §1 锁定）。
- 终端输出 / 日志 / commit message 用英文（便于 grep）。
- 报告章节固定中文标题；evidence ref ID 用 ASCII (`EV-NNNN`)。