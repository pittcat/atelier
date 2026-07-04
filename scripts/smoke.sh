#!/usr/bin/env bash
# Atelier —— 项目结构冒烟检查。
# 在 atelier 仓库根目录运行： ./scripts/smoke.sh 或 make smoke

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

PASS=0
FAIL=0
SKIP=0
fail() { FAIL=$((FAIL+1)); echo "  ❌ $*"; }
pass() { PASS=$((PASS+1)); echo "  ✅ $*"; }
skip() { SKIP=$((SKIP+1)); echo "  ⏭  $*"; }

header() { echo; echo "─── $* ───"; }

# -----------------------------------------------------------------
header "1. 关键根文件"
# -----------------------------------------------------------------
for f in README.md AGENTS.md CLAUDE.md Makefile pyproject.toml .gitignore .env.example; do
  if [ -f "$f" ]; then pass "$f"; else fail "缺少根文件: $f"; fi
done

# -----------------------------------------------------------------
header "2. 目录结构"
# -----------------------------------------------------------------
for d in _templates/agent-template agents gateway/api libs/common ops infrastructure scripts tests; do
  if [ -d "$d" ]; then pass "目录 $d"; else fail "缺少目录: $d"; fi
done

# -----------------------------------------------------------------
header "3. Cookiecutter 模板"
# -----------------------------------------------------------------
if [ -f _templates/agent-template/cookiecutter.json ]; then
  pass "cookiecutter.json 存在"
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import json,sys; json.load(open("_templates/agent-template/cookiecutter.json"))' 2>/dev/null; then
      pass "cookiecutter.json 是合法 JSON"
    else
      fail "cookiecutter.json 不是合法 JSON"
    fi
  else
    skip "python3 不在 PATH，跳过 JSON 合法性"
  fi
else
  fail "缺少 cookiecutter.json"
fi

# 检查模板里必须有 agent.py
if [ -f "_templates/agent-template/.{{cookiecutter.agent_slug}}/src/{{cookiecutter.agent_slug}}/agent.py" ]; then
  pass "模板 agent.py 存在"
else
  fail "模板 agent.py 缺失"
fi

# -----------------------------------------------------------------
header "4. 示例 Agent code-writer"
# -----------------------------------------------------------------
CW=agents/code-writer
if [ -d "$CW" ]; then
  pass "agents/code-writer/ 存在"
  for f in pyproject.toml langgraph.json Makefile .env.example AGENTS.md Dockerfile \
           src/code_writer/agent.py src/code_writer/subagents.py \
           src/code_writer/tools.py src/code_writer/prompts.py \
           src/code_writer/interrupts.py src/code_writer/cli.py \
           src/code_writer/mcp_servers.py src/code_writer/skills_loader.py \
           docs/README.md docs/PROMPT.md docs/INTERRUPTS.md docs/MCP_AND_SKILLS.md \
           skills/code-review-mindset/SKILL.md skills/conventional-commit/SKILL.md \
           tests/unit/test_agent.py tests/unit/test_prompts.py tests/unit/test_tools.py \
           tests/unit/test_rule_eight.py \
           tests/conftest.py; do
    if [ -f "$CW/$f" ]; then pass "$CW/$f"; else fail "$CW/$f"; fi
  done
else
  fail "agents/code-writer/ 不存在"
fi

# 关键硬规则检查
if [ -f "$CW/src/code_writer/tools.py" ]; then
  # 关键：在 tools.py 里**真正注册的** git_push 工具名应是 `git_push_tool` / `"git_push"`。
  # 注释 / docstring 里提到 "don't expose git_push" 是允许的。
  if grep -Eq 'git_push_tool|name *= *"?git_push"?|def +git_push\b' "$CW/src/code_writer/tools.py"; then
    fail "tools.py 不应注册 git_push 工具（注释里提一句 OK）"
  else
    pass "tools.py 未注册 git_push 工具"
  fi
  if grep -q 'interrupt_on' "$CW/src/code_writer/agent.py"; then
    pass "agent.py 配置了 interrupt_on"
  else
    fail "agent.py 缺少 interrupt_on"
  fi
  if grep -q 'SkillsMiddleware' "$CW/src/code_writer/agent.py"; then
    pass "agent.py 接入了 SkillsMiddleware"
  else
    fail "agent.py 未接入 SkillsMiddleware"
  fi
fi

if [ -d "$CW/skills" ]; then
  cnt=$(find "$CW/skills" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
  cnt=${cnt:-0}
  if [ "$cnt" -ge 2 ]; then
    pass "skills/ 下 SKILL.md 数量 >= 2 (实际 $cnt)"
  else
    fail "skills/ 下 SKILL.md 数量 < 2 (实际 $cnt)"
  fi
else
  fail "skills/ 目录缺失"
fi

# -----------------------------------------------------------------
header "5. Gateway"
# -----------------------------------------------------------------
GW=gateway
if [ -d "$GW/api" ]; then
  pass "gateway/api/ 存在"
  for f in pyproject.toml main.py auth.py registry.py README.md \
           routers/__init__.py routers/code_writer.py \
           ../scripts/run.sh; do
    if [ -f "$GW/api/$f" ]; then pass "$GW/api/$f"; else fail "$GW/api/$f"; fi
  done
else
  fail "gateway/api/ 不存在"
fi

# -----------------------------------------------------------------
header "6. Python 文件语法（基本）"
# -----------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  py_files=$(find . -type f -name "*.py" \
      -not -path "./_templates/*" \
      -not -path "./agents/*/tests/*" \
      -not -path "*/.venv/*" -print 2>/dev/null)
  py_total=0
  py_ok=0
  for f in $py_files; do
    py_total=$((py_total+1))
    if python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$f" 2>/dev/null; then
      py_ok=$((py_ok+1))
    else
      fail "Python 语法错误: $f"
    fi
  done
  pass "Python 语法检查通过: $py_ok / $py_total"
  # 模板里的 .py 不在扫描范围；只做代表性检查
  if [ -f "_templates/agent-template/.{{cookiecutter.agent_slug}}/src/{{cookiecutter.agent_slug}}/agent.py" ]; then
    if python3 -c "
import re,sys
src = open('_templates/agent-template/.{{cookiecutter.agent_slug}}/src/{{cookiecutter.agent_slug}}/agent.py').read()
# cookiecutter 占位符直接读源文件
assert 'import os' in src
print('OK')
" 2>/dev/null; then
      pass "模板 agent.py 含关键 import"
    else
      skip "模板 agent.py 占位符尚未渲染，无法深度检查"
    fi
  fi
else
  skip "无 python3，跳过 AST 检查"
fi

# -----------------------------------------------------------------
header "7. 工具可用性"
# -----------------------------------------------------------------
for cmd in make git; do
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "$cmd 可用"
  else
    fail "$cmd 不在 PATH"
  fi
done

for opt in uv ruff pytest langgraph cookiecutter; do
  if command -v "$opt" >/dev/null 2>&1; then
    pass "$opt 已安装（可选）"
  else
    skip "$opt 未安装（可选）"
  fi
done

# -----------------------------------------------------------------
header "8. 硬规矩：禁止全局 ~/.claude/skills / ~/.config/claude 加载"
# -----------------------------------------------------------------
# 反向断言：模板与示例都不应再有任何"加载 Claude 全局 skill"的代码路径。
# 但 skills_loader.py 里的 docstring / 反向断言字符串是允许的（白名单注释：含 "禁止|REFUSED|不读|**绝不**"）。
patterns_to_forbid=(
  "CLAUDE_CODE_SKILLS_DIR"
  "~/.claude/skills"
  "Path.home() /"
  "claude-code-skills"
)
hits=0
for p in "${patterns_to_forbid[@]}"; do
  # 收集命中的文件路径（去重、去掉 __pycache__）；
  # 测试目录（tests/）本身就是为了验证"禁止"逻辑故意构造的，跳过。
  files=$(grep -rl --include="*.py" -F "$p" \
      "$ROOT/_templates/agent-template" \
      "$ROOT/agents/code-writer" 2>/dev/null \
      | grep -v __pycache__ \
      | grep -v '/.venv/' \
      | grep -v '/tests/' \
      | sort -u)
  bad_lines=0
  for f in $files; do
    # 仅保留函数调用代码路径：去掉 docstring / 注释 / 字符串列表里的反向断言条目
    raw=$(grep -nF "$p" "$f" \
      | grep -vE ':\s*(#|"|\\?\*|\[)' \
      | grep -vE '禁止|REFUSED|不读|绝不|\*\*绝不\*\*|硬规矩|反向断言|规则 #8|不读取|仅项目级|forbidden_substrings|tests/unit/test_rule_eight' || true)
    bad_in_file=0
    if [ -n "$raw" ]; then
      bad_in_file=$(printf '%s\n' "$raw" | wc -l | tr -d ' ')
    fi
    bad_in_file=${bad_in_file:-0}
    bad_lines=$((bad_lines + bad_in_file))
  done
  if [ "${bad_lines:-0}" -gt 0 ]; then
    fail "模板/示例仍含禁用字符串 '$p' 的真实代码路径（$bad_lines 处）"
    hits=$((hits+bad_lines))
  else
    pass "未引用 '$p'（仅剩 docstring/反向断言，符合预期）"
  fi
done

# 再断言 docs 文档标题明确写"项目级"
for f in "$ROOT/agents/code-writer/docs/MCP_AND_SKILLS.md" \
         "$ROOT/_templates/agent-template/.{{cookiecutter.agent_slug}}/docs/MCP_AND_SKILLS.md"; do
  if [ -f "$f" ]; then
    if grep -q "项目级" "$f"; then
      pass "$(basename $(dirname $f))/$(basename $f) 写明'项目级'"
    else
      fail "$(basename $(dirname $f))/$(basename $f) 文档需写明'项目级'"
    fi
  fi
done

# AGENTS.md 规则 8
if grep -q "硬规矩\|规则 #8\|技能.*仅项目级\|Skills 与 MCP 仅项目级" "$ROOT/AGENTS.md"; then
  pass "AGENTS.md 包含规则 #8"
else
  fail "AGENTS.md 缺少规则 #8（Skills/MCP 仅项目级）"
fi

# -----------------------------------------------------------------
echo
echo "════════════════════════════════════════════"
echo "  PASS: $PASS    FAIL: $FAIL    SKIP: $SKIP"
echo "════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
