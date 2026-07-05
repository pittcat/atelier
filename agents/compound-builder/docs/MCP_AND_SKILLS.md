# Compound Builder — MCP 与 Skills 使用手册

> **项目级** — 仅加载项目内 skills / MCP。**绝不**读取用户级 / 全局级配置
> (AGENTS.md 规则 #8 / Plan R24)。本声明位于文件第 1 段,任何 reviewer / 自动化
> 检查可以 1 眼确认。

## 硬规矩(AGENTS.md #8)

**只加载项目级** Skill 与 MCP。**绝不**从以下位置加载:

- `~/.claude/skills/`
- `~/.config/claude/mcp.json`
- `CLAUDE_CODE_SKILLS_DIR`、`CLAUDE_CODE_MCP_DIR`
- 任何指向 `~/.claude/*`、`/Users/.../.config/claude/*` 的路径

`skills_loader.py` 在启动期会对 source 路径做反向断言,违规则抛
`RuntimeError: REFUSED ... Atelier AGENTS.md rule #8`。

## 1. Skills 加载

允许的来源只有两种:

| 来源 | 控制方式 | 默认 |
|------|---------|------|
| 本地项目内 skills 目录 | `./skills` 或 env `ATELIER_LOCAL_SKILLS_DIR` | `./skills` (若存在) |
| 显式声明的 GitHub 仓库 | env `ATELIER_SKILLS_GITHUB=owner/repo@ref` | 关 |

Compound Builder 不在 StateGraph 主节点调用 `load_skill`(plan KTD-7 脱钩 Deep
Agents),目前 skills 仅作为未来扩展接口保留。

## 2. MCP 服务器

### 启停(写在 `.env`)

```bash
COMPOUND_BUILDER_MCP_DISABLED=1   # 全部关
COMPOUND_BUILDER_MCP_DOCS=0       # 单开 docs(默认通过 cookiecutter 关闭)
COMPOUND_BUILDER_MCP_GITHUB=0     # 单独开 GitHub(默认关)
COMPOUND_BUILDER_MCP_FILESYSTEM=0 # 单独开 filesystem(默认关)
```

本 Agent 在 Phase 1 阶段未启用任何 MCP server(留 future expansion 入口)。

### 加新 MCP server

在 `mcp_servers.py` 的 `all_mcp_servers()` 里 push 一个 `MCPServer(...)`,
懒加载由 `tools.py` 装配(plan R24)。

## 3. 加新 skill

```
agents/compound-builder/skills/<slug>/SKILL.md
```

最小 frontmatter:

```yaml
---
name: <skill id>
description: 一句话说明何时用本 skill。
metadata:
  category: review
  tier: standard
---
```

也可从 GitHub 加载(前提是该仓库的 `SKILL.md` 满足格式):

```env
ATELIER_SKILLS_GITHUB=your-org/agent-skills@v1
```

## 4. 调试

```bash
python -c "from compound_builder.skills_loader import all_skill_sources; \
import json; print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))"

python -c "from compound_builder.mcp_servers import all_mcp_servers; \
import json; print(json.dumps([s.__dict__ for s in all_mcp_servers()], indent=2))"
```

尝试把本地路径指向 `~/.claude/skills` 会收到
`RuntimeError: REFUSED ... Atelier AGENTS.md rule #8`。

## 5. 反向断言自检

`scripts/smoke.sh` 段 8 对 `~/.claude/skills`、`CLAUDE_CODE_SKILLS_DIR`、
`Path.home() /`、`claude-code-skills` 字符串做反向断言;段 9 在
`agents/compound-builder/` 子树上独立跑同一断言。

如未来给 compound-builder 增加第三种 skill 来源,**先改 smoke.sh 段 8 + 段 9
白名单** 再写实现。
