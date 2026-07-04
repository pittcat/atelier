# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库性质

Atelier = 多 Agent 工作流编排平台 monorepo。每个 Agent 都是基于 Deep Agents / LangGraph 的独立包,共享一套 LLM 客户端 / Tracing / 规约,通过统一 FastAPI Gateway 对外暴露。

**进入仓库第一件事**: 读 `AGENTS.md`(项目宪法,优先级高于本文件)。本文件聚焦"Claude Code 操作这个仓库的具体命令 + 架构地图",不重复宪法条目。

## 高层架构

```
atelier/
├── _templates/agent-template/      # cookiecutter 脚手架(一份命令新建一个 Agent)
├── agents/<slug>/                   # 每个 Agent 一份独立包,自带 pyproject/Makefile/langgraph.json
│   ├── src/<slug>/
│   │   ├── agent.py                # create_deep_agent(...) 主图,langgraph.json 入口
│   │   ├── subagents.py            # 子代理清单(默认 researcher/tester/reviewer 三件套)
│   │   ├── tools.py                # 工具集(注意:git_push 永远不暴露)
│   │   ├── prompts.py              # 系统提示拆出来(便于版本化)
│   │   ├── interrupts.py           # interrupt_on 映射(仅 declare,具体由 create_deep_agent 装配)
│   │   ├── checkpointer.py         # MemorySaver / PostgresSaver
│   │   ├── llm.py / tracing.py     # LLM 客户端 + LangSmith 初始化
│   │   ├── mcp_servers.py          # MCP servers(懒加载)
│   │   ├── skills_loader.py        # SkillsMiddleware 的 skill sources
│   │   └── cli.py                  # python -m <slug>.cli run / replay
│   ├── tests/{unit,integration}/
│   └── docs/{README,PROMPT}.md
├── gateway/api/                     # FastAPI 统一网关
│   ├── main.py                     # app 入口、/health、/agents 列表
│   ├── registry.py                 # slug → agent 的懒加载映射
│   ├── routers/<slug>.py           # 每个 Agent 的路由(threads/runs/state/history)
│   └── auth.py                     # Bearer token 鉴权(env: GATEWAY_AUTH_TOKEN)
├── libs/common/src/common/         # 跨 Agent 共享库(LLM 客户端、tracing、auth utils)
├── infrastructure/{docker,langgraph-up}/  # 部署资产
├── ops/{runbooks,logs}/
├── scripts/smoke.sh                # 项目结构冒烟检查
└── tests/test_atelier_layout.py    # 顶层结构性测试
```

**uv workspace 多包结构**(`pyproject.toml`): `agents/*`、`gateway/api`、`libs/common` 互相通过 `atelier-common` 共享,不直接 import 彼此。

## 常用命令

所有命令在仓库根目录运行(顶层 `Makefile` 用 `find ... xargs` 递归触发各子包)。

### 开发循环

```bash
make smoke             # 结构冒烟(./scripts/smoke.sh):检查根文件/目录/cookiecutter 合法性
make format            # 全仓 ruff format
make lint              # 全仓 ruff check + mypy
make test              # 全仓 pytest(顶层 tests/ 是结构测试,各 agent 子目录也有 tests)
```

### 跑单个 Agent 的某个测试

```bash
cd agents/<slug>
TEST=tests/unit/test_tools.py make test
```

每个 Agent 子目录的 `Makefile` 都支持 `TEST=path` 变量。

### 起新 Agent

```bash
make new-agent                                     # cookiecutter 引导
# 或者直接:
cookiecutter _templates/agent-template/
```

模板会问:`agent_slug` / `agent_pascal` / `agent_display_name` / 模型选择 / 是否开 MCP / checkpointer 类型 / 是否 enable interrupt。生成后:

1. `cd agents/<slug> && uv sync`
2. `cp .env.example .env` 填 `ANTHROPIC_API_KEY` + `LANGSMITH_API_KEY`
3. 在 `gateway/api/registry.py` 的 `AGENT_REGISTRY` 加 slug 条目
4. 在 `gateway/api/routers/<slug>.py` 加 router
5. 在 `gateway/api/routers/__init__.py` 的 `ALL_ROUTERS` 注册

### 本地运行某个 Agent

```bash
make dev AGENT=<slug>                             # = cd agents/<slug> && langgraph dev
# LangGraph Studio 监听 http://localhost:2024
```

或 CLI:

```bash
cd agents/<slug> && uv sync && python -m <slug_underscored>.cli run "一段话"
cd agents/<slug> && python -m <slug_underscored>.cli replay <thread_id>
```

### 启 Gateway

```bash
make gateway                                       # uvicorn gateway/api/main:app --reload --port 8080
```

或带鉴权:

```bash
GATEWAY_AUTH_TOKEN=$(openssl rand -hex 32) LANGSMITH_TRACING=true \
  uvicorn gateway.api.main:app --reload --port 8080
```

未配置 `GATEWAY_AUTH_TOKEN` 时开发模式放行;生产必须配置。

### 部署

```bash
make build AGENT=<slug>                            # 构建 atelier/<slug> 镜像
make up    AGENT=<slug>                            # 启动 langgraph up
```

## 硬约束(必须在每次任务中遵守)

来自 `AGENTS.md` 第 1-7 条 + `agents/<slug>/AGENTS.md`,Claude Code 必须遵守:

1. **不写跨 Agent import**: `from agents.<other> import ...` 禁止。跨 Agent 协调走 `gateway/api` HTTP。
2. **不开 auto-push**: 所有 `git push` 必须人工批准;`git_commit` 是 Agent 工具,但 `git_push` 工具**永远不在 `tools.py` 里注册**(已被 smoke.sh + test_atelier_layout 校验)。
3. **prompt 改动必同步 `docs/PROMPT.md`**: 任何对 `agents/<slug>/src/<slug>/prompts.py` 的改动必须在 `agents/<slug>/docs/PROMPT.md` 末尾追加变更记录表。
4. **checkpointer 必开**: 本地 `MemorySaver`,生产 `PostgresSaver`(`ATELIER_CHECKPOINTER_URL` 切换)。
5. **interrupt_on 必配**: `bash` / `write_file` / `edit_file` / `git_commit` 至少这四个默认要 `interrupt_on=True`。模板里 `agent.py` 通过 cookiecutter `enable_interrupt=yes/no` 决定是否硬编码。
6. **路径用 `pathlib.Path`**: 跨平台,禁止硬编码 `/` 或 `\\`。
7. **中文用户用中文回复**;commit message / 终端日志用英文。
8. **依赖改动写进 `pyproject.toml`**: 不要 inline pip install。
9. **不在 main 直接改**: 开分支、提 PR、等 CI 全绿。

## Prompt 改动 SOP

1. 改 `agents/<slug>/src/<slug>/prompts.py`。
2. 在 `agents/<slug>/docs/PROMPT.md` 的"变更记录"表追加一行: 日期 / 版本 / 改动 / 原因。
3. 上 LangSmith Evaluator 跑 A/B,确认不退化再合入。

## 调试流程

| 现象 | 首选 |
|------|------|
| Agent 行为不对 | LangGraph Studio 重放 (`langgraph dev` → http://localhost:2024) + LangSmith trace |
| 想看完整 thread 历史 | `python -m <slug>.cli replay <thread_id>` 或 Gateway `GET /agents/<slug>/threads/<tid>/history` |
| 检查项目结构 | `make smoke` 或 `pytest tests/test_atelier_layout.py -q` |
| 单 Agent 测试失败 | `cd agents/<slug> && TEST=tests/unit/test_xxx.py make test` |
| 跑通不了、找不到文件 | 先 `make smoke`,看 `scripts/smoke.sh` 的输出 |
| 已知 bug / 多组件交互出错 | 看 `docs/solutions/`(按 category 组织的 post-mortems,YAML frontmatter 含 `module` / `tags` / `problem_type`) |
| 项目核心术语(`Agent` / `SubAgent` / `LangGraph Studio` / `Checkpointer` 等) | `CONCEPTS.md` 在仓库根 |

## Env 关键变量

顶层 `.env.example` 列举;每个 Agent 子目录有独立 `.env.example`,**子目录覆盖顶层**。

| 变量 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | LLM Provider key(必填,否则 agent.py 启动失败) |
| `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` | trace 必填 |
| `LANGSMITH_PROJECT` | 默认 `atelier-<slug>` |
| `ATELIER_DEFAULT_MODEL` / `ATELIER_SUBAGENT_MODEL` | 主代理 / 子代理模型,默认 `claude-opus-4-8` / `claude-haiku-4-5-20251001` |
| `ATELIER_CHECKPOINTER_URL` | 留空 → MemorySaver;填 postgres URL → PostgresSaver |
| `ATELIER_WORKDIR` | 工具执行的工作目录根(防止路径逃逸) |
| `ATELIER_INTERRUPT_DEFAULT` | 全局是否开 interrupt |
| `GATEWAY_AUTH_TOKEN` | 未配置则 dev 模式放行;生产必填 |

## 子代理设计

模板默认三件套(深度 ≤ 2,每个 ≤ 5 工具,sub 之间不互相调用):

| 名字 | 职责 | 工具 |
|------|------|------|
| `researcher` | 仓库/文档调研,只读 | search_codebase / search_docs / read_file |
| `tester`     | 写并跑测试 | read_file / write_file / run_tests / lint |
| `reviewer`   | 审 diff(correctness/perf/security) | read_file / search_codebase / lint |

修改子代理清单见 `agents/<slug>/src/<slug>/subagents.py`。

## MCP / Skills

模板支持本地 `./skills/` + Claude Code 全局 `~/.claude/skills/` + GitHub 远程三种 skill 来源,通过 `skills_loader.py` + `SkillsMiddleware` 装配。MCP servers 在 `mcp_servers.py` 懒加载。详见模板生成后的 `docs/MCP_AND_SKILLS.md`。

## 按需读上游源码

仓库根的 `.source_code` 文件列出本地拉下来的上游库(每行一个绝对路径,例如 `/Users/pittcat/Dev/Python/deepagents`)。**不是每次回答都去读**,只在以下情况才打开:

- 用户直接问 `.source_code` 里某个库怎么用、或问"我的代码用 X 失败了"。
- 用通用知识回答过一次,再答一次仍不自洽(两次答案冲突) —— 这时去翻源码核对,不要继续猜。
- review / test 阶段,代码改动触到某个上游库,改动里有对该库 API / 行为的假设。

默认走通用知识;触发条件命中再读,读完把结论和路径回给用户(便于人复核)。

## 与全局 CLAUDE.md 的关系

顶层 `~/.claude/CLAUDE.md` 的全局规约(中文回答、Mermaid 验证、RTK 工具优先、Memory 操作、压缩规则等)在本仓库**全部继承**,优先级仍按:用户指令 > 本仓库 `AGENTS.md` > 本文件 > 全局 `CLAUDE.md`。