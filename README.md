# Atelier — 多 Agent 工作流编排平台

> **Atelier**（法语：工坊）—— 每个 Agent 都是一间独立工坊，统一调度、按需协作。

## 这是什么

这是一个 monorepo：把"用 Deep Agents / LangGraph 写的多个独立 Agent"打包成可独立部署、可共享前端、可统一运维的工作流平台。

适合：

- 想做一组专业 Agent（写代码、审 PR、写文档、查数据……），
- 每个 Agent 都有自己的工具集、子代理、提示词、测试、部署，
- 希望它们独立演进，但共享同一份 LLM 客户端 / 追踪 / 仓库规约。

## 目录速览

```
atelier/
├── _templates/agent-template/        # cookiecutter 脚手架：一份命令新建一个 Agent
├── agents/                           # 所有 Agent 本体
│   ├── code-writer/                  # 示范 Agent（真实可跑通）
│   └── ...
├── gateway/api/                      # 统一对外 FastAPI 网关
├── libs/common/                      # 共享库（LLM 客户端、追踪、auth）
├── infrastructure/                   # Docker / K8s / langgraph up
├── ops/                              # runbook / 日志
├── tests/                            # 跨 Agent 端到端测试
├── scripts/                          # 一键脚本（新建 Agent、smoke test）
├── Makefile                          # make format / lint / test 全仓统一
├── pyproject.toml                    # uv workspace 多包
└── README.md                         # 你现在看到的这个文件
```

## 快速开始

### 1. 安装前置

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)（推荐）或 Poetry
- [cookiecutter](https://cookiecutter.readthedocs.io/)（`uv tool install cookiecutter`）

### 2. 新建一个 Agent

```bash
cookiecutter _templates/agent-template/
# 提示输入：agent slug / 显示名 / 描述
# 一秒后：agents/<slug>/ 整个目录已经准备好
cd agents/<slug> && uv sync && make test
```

### 3. 本地跑示范 Agent

```bash
cd agents/code-writer
uv sync
cp .env.example .env  # 填入 LLM Provider Key + LangSmith
langgraph dev         # http://localhost:2024  → LangGraph Studio
```

### 4. 用脚本一次性自检

```bash
./scripts/smoke.sh    # 校验项目结构、依赖、关键文件
```

## 核心约定（速查）

| 约定 | 说明 |
|------|------|
| **每个 Agent 独立** | 不允许 `from agents.<other> import ...`，只能 `from libs.common import ...` |
| **永远不开 auto-push** | 所有 git push 必须人工；commit OK |
| **每 Agent 必带 docs/PROMPT.md** | prompt 改动必须同步到文档 |
| **checkpointer 必开** | MemorySaver 起步，团队化用 PostgresSaver |
| **断点回放用 LangGraph Studio + LangSmith trace** | 不要自己造 log 系统 |

## 命令手册

```bash
# 创建新 Agent
cookiecutter _templates/agent-template/

# 全仓统一 check
make format    # 格式化
make lint      # ruff + mypy
make test      # 全仓测试

# 仅某个 Agent
cd agents/code-writer
TEST=tests/unit/test_tools.py make test

# 本地开发某个 Agent
cd agents/code-writer && langgraph dev

# 部署某个 Agent
cd agents/code-writer && langgraph build -t atelier/code-writer
                          && langgraph up

# 起一个统一的 gateway（本地）
cd gateway/api && uvicorn main:app --reload --port 8080
```

## 设计文档

- `docs/PLATFORM_GUIDE.md`（待生成）：如何加新 Agent / 怎么部署 / 怎么 debug
- `_templates/agent-template/docs/PROMPT.md`：每个 Agent 的提示词运维手册
- `AGENTS.md`：本仓库给 AI Agent 看的宪法
- `CLAUDE.md`：Claude Code 等会话级规约

---

> 进入这个仓库之前，先读 `AGENTS.md`。
> 改任何 Agent 之前，先看 `docs/PROMPT.md`。
> 出问题之前，先开 LangGraph Studio + LangSmith。
