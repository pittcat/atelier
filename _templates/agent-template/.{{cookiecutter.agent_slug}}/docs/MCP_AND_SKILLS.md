# {{ cookiecutter.agent_pascal }} —— MCP 与 Skills 使用手册

## 硬规矩（AGENTS.md #8）

**只加载项目级** Skill 和 MCP。**绝不**从以下位置加载：

- `~/.claude/skills/`
- `~/.config/claude/mcp.json`
- `CLAUDE_CODE_SKILLS_DIR`、`CLAUDE_CODE_MCP_DIR`
- 任何指向 `~/.claude/*`、`/Users/.../.config/claude/*` 的路径

`skills_loader.py` 在启动期会对 source 路径做反向断言，违规则抛 `RuntimeError`。

## 1. Skills 加载

允许的来源只有两种：

| 来源 | 控制方式 | 默认 |
|------|---------|------|
| 本地项目内 skills 目录 | `{{ cookiecutter.load_local_skills_dir }}` 或 env `ATELIER_LOCAL_SKILLS_DIR` | `./skills`（若存在） |
| 显式声明的 GitHub 仓库 | `{{ cookiecutter.load_skills_from_github }}` 或 env `ATELIER_SKILLS_GITHUB=owner/repo@ref` | 关 |

运行时主代理调 `load_skill(name)` 按需读 `SKILL.md`。

## 2. MCP 服务器

默认配置（cookiecutter 控制）：

{% if cookiecutter.include_mcp_github == "yes" -%}
- ✅ GitHub MCP（`mcp__github__*` 工具集：pr / issue / search_file）
{% endif %}
{% if cookiecutter.include_mcp_docs == "yes" -%}
- ✅ Docs fetch MCP（`mcp__docs_langchain__fetch` 工具，URL 限于 docs.langchain.com）
{% endif %}
{% if cookiecutter.include_mcp_filesystem == "yes" -%}
- ✅ Filesystem MCP（`mcp__filesystem__*`，根目录由 `ATELIER_WORKDIR` 控制）
{% endif %}
{% if cookiecutter.include_mcp_github == "no" and cookiecutter.include_mcp_docs == "no" and cookiecutter.include_mcp_filesystem == "no" -%}
- 无
{% endif %}

### 启停（写在 `.env`）

```bash
{{ cookiecutter.agent_upper }}_MCP_DISABLED=1            # 全部关
{{ cookiecutter.agent_upper }}_MCP_GITHUB=0             # 单独关 GitHub
{{ cookiecutter.agent_upper }}_MCP_DOCS=1               # 单独开
{{ cookiecutter.agent_upper }}_MCP_FILESYSTEM=1         # 单独开
```

## 3. 加新 MCP server

在 `mcp_servers.py` 的 `all_mcp_servers()` 里 push 一个 `MCPServer(...)`：

```python
MCPServer(
    name="slack",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-slack"],
    env={"SLACK_TOKEN": os.getenv("SLACK_TOKEN", "")},
    description="Slack MCP (project-level)",
)
```

启动时由 `tools.py:_mcp_tools()` 拉起（懒加载、stdio）。

## 4. 加新 skill

```
agents/{{ cookiecutter.agent_slug }}/skills/<slug>/SKILL.md
```

最小 frontmatter：

```yaml
---
name: <skill id>
description: 一句话说明何时用本 skill。
metadata:                  # 可选
  category: review
  tier: standard
---
```

也可从 GitHub 加载（前提是把该仓库的 SKILL.md 摆好）：

```env
{{ cookiecutter.agent_upper }}_SKILLS_GITHUB=your-org/agent-skills@v1
```

## 5. 调试

```bash
python -c "from {{ cookiecutter.agent_slug }}.skills_loader import all_skill_sources; \
import json; print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))"

python -c "from {{ cookiecutter.agent_slug }}.mcp_servers import all_mcp_servers; \
import json; print(json.dumps([s.__dict__ for s in all_mcp_servers()], indent=2))"
```

尝试把本地路径指向 `~/.claude/skills` 会收到 `RuntimeError: REFUSED ... Atelier AGENTS.md rule #8`。
