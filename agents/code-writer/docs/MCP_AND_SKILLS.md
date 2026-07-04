# Code Writer —— MCP 与 Skills

> 严格按 AGENTS.md 规则 #8：**只加载项目级** skill 和 MCP，**绝不**读全局配置。

## Skills（按需注入）

主代理内置 `load_skill(name)` 工具，可用 source 仅两种：

| Source | 触发 | 备注 |
|--------|------|------|
| `agents/code-writer/skills/` | 总是（若存在） | 项目内；可在 `.env` 用 `ATELIER_LOCAL_SKILLS_DIR=path` 覆盖（必须落在项目根下） |
| GitHub 仓库（项目级声明） | 设 `ATELIER_SKILLS_GITHUB=owner/repo@ref` | 仓库里放 `SKILL.md` 即被识别 |

主代理会自动：
1. 从 source 读取每个 skill 的 frontmatter（`name` / `description`）。
2. 给主代理 `load_skill(name)` 工具按需调用。
3. 把 `SKILL.md` 正文当上下文注入。

> ⛔ **不**读 `~/.claude/skills/`。  
> ⛔ **不**读 `CLAUDE_CODE_SKILLS_DIR`。  
> ⛔ **不**接受任何指向 `~/.claude/*`、`/Users/.../.config/claude/*` 的路径。  
> 违反规则 #8 会在 `skills_loader.py` 启动期直接抛 `RuntimeError`。

### 列出现在装好的 skill

```bash
python -m code_writer.skills_loader
```

### 加新 skill

```
agents/code-writer/skills/<slug>/SKILL.md
```

前置 frontmatter：

```yaml
---
name: <skill id>
description: 一句话说明何时用本 skill。
metadata:                  # 可选
  category: review
  tier: standard
---
```

## MCP（外部工具）

四个开关（写在 `.env`）：

```bash
ATELIER_MCP_DISABLED=0     # 1 = 全关
ATELIER_MCP_GITHUB=0       # 1 = 启用 GitHub MCP
ATELIER_MCP_DOCS=0         # 1 = 启用 docs fetch MCP
ATELIER_MCP_FILESYSTEM=0   # 1 = 启用 filesystem MCP
```

启用的 server 由 `mcp_servers.py:all_mcp_servers()` 显式注册，工具前缀为 `mcp__<name>__<tool>`。

> ⛔ **不**读 `~/.config/claude/mcp.json`、`~/.claude/mcp.json` 等全局 MCP 配置。

### 加新 MCP server

改 `src/code_writer/mcp_servers.py` 的 `all_mcp_servers()`：push 一个 `MCPServer(...)`。

## 调试

```bash
python -c "from code_writer.skills_loader import all_skill_sources; \
import json; print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))"

python -c "from code_writer.mcp_servers import all_mcp_servers; \
import json; print(json.dumps([s.__dict__ for s in all_mcp_servers()], indent=2))"
```
