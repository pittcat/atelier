# Code Writer Agent —— Atelier 平台宪法子集

1. 永远不开 auto-push。
2. prompt / tool / subagent 改动必须同步 docs/PROMPT.md。
3. bash / write_file / edit_file / git_commit 必须配 interrupt_on。
4. 不允许引用其他 Agent（`from agents.<other> import ...` 会被 lint 拒收）。
5. 写代码前先 explore；explore 路径走 `read_file` / `Glob` / `Grep`。
6. 中文用户用中文回复；commit message 走 conventional commits（强制英文）。
