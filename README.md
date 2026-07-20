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
│   ├── compound-builder/              # 多阶段 TDD 编排 Agent
│   └── modem-log-analyzer/            # NuttX Modem 失败日志分析 Agent (CLI-first)
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

## 已交付的 Agent

### code-writer（示范 Agent）

`agents/code-writer/`：规划 → 实现 → 测试 → commit。

```bash
cd agents/code-writer
uv sync
cp .env.example .env
make dev   # Studio: http://localhost:2024
```

### compound-builder（多阶段 TDD 编排）

`agents/compound-builder/`：10 节点 StateGraph + 6 维 Send 并行 review + ship gating。

```bash
cd agents/compound-builder
uv sync
make test   # 含 plan-driven TDD
```

### modem-log-analyzer（NuttX Modem 失败日志分析，CLI-first）

`agents/modem-log-analyzer/`：嵌入式测试工程师的工具，分析单次 EVB 失败日志并产出
中文 `report.md` + 机器可读 `analysis.json`。

```bash
# CLI 主入口
modem-log-analyzer analyze --evb-log evb.log --output out/

# 带控制脚本日志 (升级为 TEST_AUTOMATION_FAILURE_CONFIRMED 的关键)
modem-log-analyzer analyze \
  --evb-log evb.log --control-log control.log \
  --output out/ --label "loop_52"

# Gateway
curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -F "artifact=@evb.log"
```

**特点**：
- 6 个诊断分类严格匹配需求 R13
- 10 章节 report.md（顺序固定）
- 只读 + 不暴露危险工具
- Interrupt/Resume 控制脚本日志按需请求
- Gateway 完整接入（7 路由 + 鉴权 + 路径穿越防护）
- 5 个脱敏 e2e fixture + 187 个测试全过

详细文档：
- `agents/modem-log-analyzer/docs/README.md` — 启动 + 快速开始
- `agents/modem-log-analyzer/docs/EXAMPLES.md` — 5 个 fixture 输入/输出
- `agents/modem-log-analyzer/docs/OPERATIONS.md` — 退出码 + 故障排查
- `agents/modem-log-analyzer/docs/PRIVACY.md` — 三层隐私边界
- `agents/modem-log-analyzer/docs/COMMAND_CATALOG.md` — 命令知识表
- `agents/modem-log-analyzer/docs/TESTING.md` — TDD 流程
- `docs/plans/2026-07-19-001-feat-modem-log-analyzer-cli-plan.md` — 9 个开发 Unit 原始 plan
- `docs/solutions/integration-issues/modem-log-analyzer-adversarial-review-2026-07-19.md` — 完成性 + 对抗性审查报告

---

> 进入这个仓库之前，先读 `AGENTS.md`。
> 改任何 Agent 之前，先看 `docs/PROMPT.md`。
> 出问题之前，先开 LangGraph Studio + LangSmith。
