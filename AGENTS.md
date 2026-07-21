# Atelier —— Agent 项目宪法

> 任何 AI Agent / 人类协作者 修改这个仓库之前**必须**完整读完这份文档。
> 它比 `README.md` 优先级更高；与具体 Agent 文档冲突时，**以本文档为准**。

## 一、硬规矩（不可违反）

1. **每个 Agent 是独立包**——禁止 `from agents.<其他> import ...`；只能 `from libs.common import ...`。
2. **永远不开 auto-push**——所有 `git push` 强制人工审批；`git commit` 可以自动。
3. **改 prompt 必须同时改文档**——`agents/<slug>/docs/PROMPT.md` 是 prompt 的真相之源；改完 prompt 要在这个文件加变更记录。
4. **checkpointer 必开**——本地 MemorySaver，生产 PostgresSaver；不允许关闭。
5. **危险动作必加 interrupt**——`bash` / `git_commit` / `write_file` / `git_push` 至少四个默认需要人工审批。
6. **不写中文文件名**——所有目录/文件用 ASCII，语义用英文。
7. **不允许第三方秘密硬编码**——所有 key 必须走 `.env` / 环境变量。
8. **Skills 与 MCP 仅项目级**——
   - **禁止**自动读取 `~/.claude/skills/`、`~/.claude/mcp.json`、`~/.config/claude/` 等任何"用户级 / 全局级"配置。
   - **禁止**用环境变量 `CLAUDE_CODE_SKILLS_DIR` / `CLAUDE_CODE_MCP_DIR` / 同类全局路径桥接到任意 Agent。
   - Skills / MCP 源必须是 `agents/<slug>/skills/`、`agents/<slug>/mcp.local.json`、或 cookiecutter 显式声明的 GitHub 仓库。
   - 任何"借用全局 skill/MCP"的代码路径必须删除；侵入性新增需要在本 AGENTS.md 提 PR 通过。
9. **禁止 AI 擅自新建 git branch**——
   - **任何** AI Agent / Subagent / Skill（含 Cursor、Claude Code、cloud agent、本仓库 `.claude/skills`、用户全局 skill）都**不得**自行执行 `git checkout -b`、`git switch -c`、`gh pr create` 附带的隐式开分支、或其它等价「新建分支」操作。
   - 只有用户**明确说**「开分支 / 新建 branch / create branch / checkout -b …」时才允许新建。
   - 默认：留在用户当前已 checkout 的分支上工作；用户说合并到 `main`/`master` 就按指令合并，不要先自作主张开 feature branch。
   - 人类协作者自己的分支/PR 流程不受此条限制；本条约束的是 **AI 不得擅作主张**。

## 二、Agent 生命周期

```
需求 → cookiecutter 起骨架 → 写 prompt (docs/PROMPT.md)
    ↓
实现 tools.py / subagents.py → 写 tests/unit + integration
    ↓
make format && make lint && make test 全过
    ↓
LangGraph Studio 跑通 → LangSmith trace 记录
    ↓
接入 gateway/api 路由 → 更新 README
    ↓
langgraph build && langgraph up 部署
```

任何一步不允许跳过。

## 三、文件组织

每个新 Agent 都遵循下面这个最小骨架（见 `_templates/agent-template/`）：

```
agents/<slug>/
├── src/<slug>/
│   ├── agent.py        # create_deep_agent(...) 主图，langgraph.json 入口
│   ├── subagents.py    # 该 Agent 引用的子代理清单
│   ├── tools.py        # 自定义工具集
│   ├── prompts.py      # 系统提示拆出来（便于版本化）
│   ├── state.py        # 自定义 State（可选）
│   └── eval/           # LangSmith 评测
├── tests/{unit,integration}/
├── docs/
│   ├── README.md       # 人类读
│   └── PROMPT.md       # AI 读
├── pyproject.toml
├── langgraph.json      # LangGraph 部署描述
├── Makefile
├── AGENTS.md           # 该 Agent 自己的宪法
├── .env.example
└── Dockerfile
```

## 四、Sub-agent 设计原则

- **深度 ≤ 2**：main → sub，禁止 sub-sub。
- **每个 subagent 单一职责**：研发 / 测试 / 评审 / 文档。
- **不要给 subagent 太多工具**：少于等于 5 个；多了拆。
- **subagent 不能互相调用**（main 可同时委派多个）。

## 五、提示词工程

- **写在 `prompts.py`**，**不要塞进 `agent.py` 的字符串里**。
- **变更走 git diff**：`docs/PROMPT.md` 末尾追加变更日志。
- **新提示词改动前先在 LangSmith Evaluator 上 A/B**。
- **不要在系统提示里塞临时上下文**——动态信息走工具 / state。

## 六、测试

| 类别 | 工具 | 时机 |
|------|------|------|
| 单元 | pytest | 每个 PR |
| 集成 | pytest + LangGraph Python SDK | 跨模块改动 |
| 端到端 | LangSmith Evaluator | 接 gateway 前 |
| 回归 | LangSmith Datasets | 每次发版 |

每个 Agent 至少覆盖：
- tool 行为
- subagent 路由（正确 task 调用）
- 状态持久化（thread 切换）
- interrupt / resume 流程

## 七、部署

| 阶段 | 命令 |
|------|------|
| 本地 | `langgraph dev` |
| 镜像 | `langgraph build -t atelier/<slug>` |
| 服务 | `langgraph up` 或 K8s Apply |
| 灰度 | gateway/api router 上加 canary header 路由 |

## 八、贡献流程

1. 读 `AGENTS.md`（这个文件）。
2. 从 `cookiecutter _templates/agent-template/` 起新 Agent。
3. **`make format && make lint && make test`** 通过才能提 PR。
4. **PR 描述必含**：动机 / 改动概览 / 测试 / 风险 / 回滚 / 关联 issue。
5. **人类提 PR 时**：描述必含动机 / 改动概览 / 测试 / 风险 / 回滚 / 关联 issue；CI 全绿再合。
6. **AI 禁止擅自开 branch**（见硬规矩 9）——在用户当前分支上改；用户明确要求合并到 `main`/`master` 时再合并。不要为了「不在 main 上直接改」而自行 `checkout -b`。

## 九、遇到问题

| 现象 | 首选 |
|------|------|
| Agent 行为不对 | LangGraph Studio 重放 + LangSmith trace |
| prompt 难调 | LangSmith Evaluator + dataset A/B |
| 找不文件 | 先 `make smoke` |
| 跨 Agent 协调 | 走 gateway API，不要直接 import |

---

> 改动这份文档请提 PR，描述改动原因；不接受 silent edit。
<!-- RALPH-BOOTSTRAP-START: ralph-pipeline v1 -->
## Ralph Pipeline Suite

This project carries a Ralph pipeline suite bootstrapped by `ralph-project-bootstrap`.

| File | Purpose |
|------|---------|
| `ralph.pipeline.yml` | Runtime config (owned keys under `_bootstrap:`) |
| `PROMPT.pipeline.md` | Managed fallback prompt (plan required via `--plan`) |
| `ralph.bootstrap.yml` | Provenance record |

**Verification commands** (must pass before reporting completion):

- `make test` — pytest
- `make lint` — ruff check + mypy
- `make smoke` — structural integrity

**Launch** (requires a real plan file):

```bash
ralph -c ralph.pipeline.yml -H builtin:ce-executor-pipeline run --plan <PLAN_PATH>
```
<!-- RALPH-BOOTSTRAP-END: ralph-pipeline -->