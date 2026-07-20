# ModemLogAnalyzer —— MCP 与 Skills

> 严格按 AGENTS.md 规则 #8：**只加载项目级** skill 和 MCP，**绝不**读全局配置。

## 1. 硬规矩（仓库宪法 #8）

- **禁止**从 `~/.claude/skills/`、`~/.config/claude/`、`CLAUDE_CODE_SKILLS_DIR`、`CLAUDE_CODE_MCP_DIR` 等位置加载。
- **禁止**用环境变量 `CLAUDE_CODE_SKILLS_DIR` / `CLAUDE_CODE_MKILLS_DIR` 桥接到本 Agent。
- 所有 skill / MCP 源必须是项目级（`agents/modem-log-analyzer/skills/`、`mcp.local.json`、或本文件显式声明的 GitHub 仓库）。
- 违反规则 #8 会在 `skills_loader.py` 启动期直接抛 `RuntimeError: REFUSED`。

`skills_loader.py` 启动期会校验每个源路径：
- 路径含 `.claude/skills` 或 `CLAUDE_CODE_SKILLS_DIR` → 拒绝
- 路径不在项目根下 → 拒绝
- 项目根的回溯上限 8 层（防止循环）

## 2. Skills（按需注入）

### 2.1 来源

| Source | 触发 | 默认 | 备注 |
|--------|------|------|------|
| 本地 `./skills` | `MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR`（默认 `./skills`） | 始终加载（若存在） | 项目内；可用 env 覆盖 |
| GitHub 仓库 | `MODEM_LOG_ANALYZER_SKILLS_GITHUB=owner/repo@ref` | 关 | 仓库里放 `SKILL.md` 即被识别 |

### 2.2 当前默认 skill

```
agents/modem-log-analyzer/skills/
├── code-review-mindset/SKILL.md   # 通用 code review 心智（从模板继承）
└── conventional-commit/SKILL.md   # Conventional Commit 规范（从模板继承）
```

两个 skill 都来自 `_templates/agent-template/`，对本 Agent 来说：
- `code-review-mindset`：审查报告结构是否符合 Plan R19。
- `conventional-commit`：未来 Agent 自动 commit 用，本 Agent 通常不需要。

实际场景中，本 Agent **几乎不调用 skill**——所有业务动作都走命令知识表 + schema-bound LLM。

### 2.3 列出现在装好的 skill

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -m modem_log_analyzer.skills_loader
```

输出示例：
```json
[
  {
    "label": "local",
    "kind": "dir",
    "location": "/path/to/agents/modem-log-analyzer/skills"
  }
]
```

或用 Python：

```python
from modem_log_analyzer.skills_loader import all_skill_sources
import json
print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))
```

### 2.4 加新 skill（项目级）

#### 2.4.1 何时加

只读分析 Agent 极少需要新 skill。当前 skill 列表：
- `code-review-mindset`（继承）
- `conventional-commit`（继承，但本 Agent 不提交）

**真正可能需要的 skill**：
- `modemcli-semantics`：项目级 ModemCLI 命令语义扩展（与 `command_catalog.py` 互补）
- `evidence-extraction`：从控制脚本日志识别证据模式

#### 2.4.2 怎么加

```
agents/modem-log-analyzer/skills/<slug>/SKILL.md
```

最小 frontmatter：

```yaml
---
name: <skill id>
description: 一句话说明何时用本 skill。
metadata:
  category: <review|diagnostic|evidence>
  tier: standard
---
```

正文用 Markdown；deepagents SkillsMiddleware 会注入到 LLM context。

#### 2.4.3 验证

```bash
# 启动期 (CLI 启动时打印)
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -m modem_log_analyzer.cli --help

# 反向断言 (CI)
TEST=tests/unit/test_skills_loader.py make test
```

### 2.5 路径覆盖示例

```python
# 试图读 ~/.claude/skills → RuntimeError
import os
os.environ["MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR"] = str(Path.home() / ".claude" / "skills")

from modem_log_analyzer.skills_loader import all_skill_sources
all_skill_sources()
# RuntimeError: REFUSED: skill path '...' references a global Claude config.
#              Atelier AGENTS.md rule #8: project-level only.
```

测试覆盖：`tests/unit/test_skills_loader.py::test_skills_loader_rejects_global_claude_path`。

## 3. MCP（外部工具）

### 3.1 默认：完全禁用

本 Agent 默认**不挂任何 MCP server**。`mcp_servers.all_mcp_servers()` 在无 env 配置时返回空列表。

```bash
# 默认 (关闭)
MODEM_LOG_ANALYZER_MCP_DISABLED=1
```

### 3.2 环境变量控制

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `MODEM_LOG_ANALYZER_MCP_DISABLED` | false | 全部关 |
| `MODEM_LOG_ANALYZER_MCP_GITHUB` | false | 开 GitHub MCP（不推荐：本 Agent 不读源码） |
| `MODEM_LOG_ANALYZER_MCP_DOCS` | false | 开 docs fetch MCP（可加：内部 Modem 文档） |
| `MODEM_LOG_ANALYZER_MCP_FILESYSTEM` | false | 开 filesystem MCP（**禁止**：本 Agent 不需要） |

### 3.3 真实可能需要的 MCP

**docs-langchain / internal-modem-docs**：从内部 Modem 协议文档站获取命令语义补充。

```bash
MODEM_LOG_ANALYZER_MCP_DOCS=1
MODEM_LOG_ANALYZER_MCP_DOCS_URL=https://modem-docs.internal.example
```

### 3.4 加新 MCP server

在 `src/modem_log_analyzer/mcp_servers.py:all_mcp_servers()` 中 push：

```python
MCPServer(
    name="docs-modem",
    command="npx",
    args=["-y", "@anthropic/mcp-server-fetch", "https://your-internal-docs.example"],
    env={},
    description="内部 Modem 文档检索（项目级）",
)
```

⚠️ 必须显式声明在 `mcp_servers.py`，**不**通过 `~/.config/claude/mcp.json` 全局配置（违反 AGENTS.md #8）。

### 3.5 反向断言

`mcp_servers.py` 静态扫描 `~/.config/claude`、`~/.claude/mcp.json` 等字符串。但反向断言字符串允许（用于文档警示）。**真正**读取全局配置的代码路径不应存在。

## 4. 调试

### 4.1 Skills 调试

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.skills_loader import all_skill_sources, to_deepagents_source
import json
sources = all_skill_sources()
print('Sources:')
for s in sources:
    print(f'  {s.label}: {s.kind} = {s.location}')
print('\\nDeepAgents sources:')
for s in sources:
    print(json.dumps(to_deepagents_source(s)))
"
```

### 4.2 MCP 调试

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.mcp_servers import all_mcp_servers
import json
servers = all_mcp_servers()
print(json.dumps([s.__dict__ for s in servers], indent=2))
"
```

若 `shutil.which(s.command)` 不存在（如 `npx` 未装），server 被静默过滤。
预期本 Agent 默认情况下输出空列表。

### 4.3 反向断言字符串

`tests/unit/test_rule_eight.py`（继承自 code-writer 模板）静态扫描：
- `~/.claude/skills` 应仅出现在反向断言
- `CLAUDE_CODE_SKILLS_DIR` 应仅出现在反向断言
- `~/.config/claude/mcp.json` 应仅出现在反向断言

任何"真正读"的代码路径会被测试拒绝。

## 5. 故障排查

### 5.1 Skill 加载失败

```
RuntimeError: REFUSED: skill path '/Users/x/.claude/skills' references a global Claude config.
```

修复：把 `MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR` 改为项目内路径或 unset。

### 5.2 MCP 启动失败

```
FileNotFoundError: [Errno 2] No such file or directory: 'npx'
```

修复：`npx` 需要 Node.js。或 `MODEM_LOG_ANALYZER_MCP_DISABLED=1` 全部关闭。

### 5.3 反向断言失败

```
ruff check:
  agents/modem-log-analyzer/src/modem_log_analyzer/skills_loader.py:60:8: G004 
  Forbidden substring used outside _assert_project_local
```

修复：在断言上下文外，不要出现 `.claude/skills` 等字符串。如必须写文档，移到反向断言 `forbidden_substrings` tuple 中。

## 6. 反模式

| 反模式 | 后果 |
| --- | --- |
| `CLAUDE_CODE_SKILLS_DIR=/path ~/.claude/skills` | Rule #8 违反；RuntimeError |
| `mcp_servers.py` import `~/.config/claude/mcp.json` | Rule #8 违反；CI 拒收 |
| skill 内容含敏感凭据 | 泄露到 GitHub |
| 依赖全局 Claude Code 配置 | 部署到无 Claude Code 环境的机器时崩溃 |
| 重复全局 skill 的内容到项目 skill | 维护成本翻倍 |