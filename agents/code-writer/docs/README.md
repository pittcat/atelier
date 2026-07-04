# Code Writer Agent

> **Code Writer** —— Atelier 平台的主代码编写 Agent：
> 接到需求 → 规划 → 实现 → 测试 → commit，**绝不 push**。

## 能力

- 主代理模型：`claude-opus-4-8`
- 子代理（subagents.py）：
  - `researcher`：仓库 / 外部文档调研（只读）
  - `tester`    ：写并跑测试 + lint
  - `reviewer`  ：diff 评审（correctness/perf/security/conventions）
- 工具集（tools.py）：
  - `read_file` / `write_file` / `edit_file`
  - `bash`（白名单 + 60s 超时 + 永久人工批准）
  - `git_status` / `git_diff` / `git_commit`
  - `run_tests` / `lint` / `search_codebase` / `search_docs`
- **危险操作全部走 `interrupt_on`**：`bash` / `write_file` / `edit_file` / `git_commit`
- **永远不开 `git_push`**：push 永远人工

## 快速开始

```bash
cd agents/code-writer
uv sync
cp .env.example .env      # 填 ANTHROPIC_API_KEY、LANGSMITH_API_KEY
make dev                  # LangGraph Studio: http://localhost:2024
# 或：python -m code_writer.cli run "把 CLAUDE.md 同步到 README"
```

## 工作流概览

```
┌──────────────┐  user message
│   main agent │ ─────────────────► plan (write_todos)
│  opus-4-8    │
└──────┬───────┘
       │ task()
       ▼
   ┌───────────┐     ┌─────────┐     ┌─────────┐
   │researcher │ …   │ tester  │ …   │ reviewer│
   │ haiku     │     │ haiku   │     │ haiku   │
   └───────────┘     └─────────┘     └─────────┘
       ▲                ▲                 ▲
       └────────────────┴─────────────────┘
                  files / diffs
```

## 测试

```bash
make test
TEST=tests/unit/test_prompts.py make test
```

集成测试默认 `pytest -q -m "not integration"` 跳过。

## 部署

```bash
make build              # 构建 atelier/code-writer 镜像
make up                 # 启动 langgraph up
```

## 文档

- `docs/PROMPT.md` —— 提示词运维手册（**prompt 改动后必须更新**）
- `docs/INTERRUPTS.md` —— 触发中断的工具清单与审批流
