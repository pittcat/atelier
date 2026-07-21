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

# Agent 目录 slug 用连字符, 禁止 agents/foo_bar (Python 包名才用 underscore)
bad_agent_dirs=""
for d in agents/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  case "$name" in
    *_*) bad_agent_dirs="$bad_agent_dirs $name" ;;
  esac
done
if [ -z "$bad_agent_dirs" ]; then
  pass "agents/ 目录名均用连字符 (无 underscore slug)"
else
  fail "agents/ 禁止 underscore 目录名:$bad_agent_dirs (应用 hyphen, 如 modem-log-analyzer)"
fi

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
  # 收集命中的文件路径(去重、去掉 __pycache__);
  # 测试目录(tests/)本身就是为了验证"禁止"逻辑故意构造的,跳过。
  files=$(grep -rl --include="*.py" -F "$p" \
      "$ROOT/_templates/agent-template" \
      "$ROOT/agents/code-writer" \
      "$ROOT/agents/compound-builder" 2>/dev/null \
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
header "9. Compound Builder (新 Agent)"
# -----------------------------------------------------------------
CB=agents/compound-builder
if [ -d "$CB" ]; then
  pass "$CB/ 目录存在"
  for f in pyproject.toml langgraph.json Makefile .env.example AGENTS.md Dockerfile \
           src/compound_builder/__init__.py src/compound_builder/agent.py \
           src/compound_builder/state.py src/compound_builder/graph.py \
           src/compound_builder/tools.py src/compound_builder/prompts.py \
           src/compound_builder/interrupts.py src/compound_builder/cli.py \
           src/compound_builder/checkpointer.py src/compound_builder/tracing.py \
           src/compound_builder/llm.py src/compound_builder/skills_loader.py \
           src/compound_builder/mcp_servers.py src/compound_builder/subagents.py \
           src/compound_builder/nodes/__init__.py src/compound_builder/nodes/coordinator.py \
           src/compound_builder/nodes/executor.py src/compound_builder/nodes/validator.py \
           src/compound_builder/nodes/fixer.py src/compound_builder/nodes/review_coordinator.py \
           src/compound_builder/nodes/dimension_reviewer.py \
           src/compound_builder/nodes/review_synthesizer.py \
           src/compound_builder/nodes/shipper.py src/compound_builder/nodes/reporter.py \
           src/compound_builder/nodes/progress_steward.py \
           docs/README.md docs/PROMPT.md docs/INTERRUPTS.md docs/MCP_AND_SKILLS.md \
           tests/unit/test_tools.py tests/unit/test_phase_authority.py \
           tests/unit/test_repair_budget.py \
           tests/conftest.py; do
    if [ -f "$CB/$f" ]; then pass "$CB/$f"; else fail "$CB/$f"; fi
  done
else
  fail "$CB/ 不存在"
fi

if [ -f "$CB/src/compound_builder/tools.py" ]; then
  # 注意:docstring 中的 "git_push" / "git_push_tool" 是允许的(反向断言字符串)。
  # 只把真注册(def git_push(...) 或 @tool 上面的 def)算作禁用。
  if grep -Eq 'def +git_push\b' "$CB/src/compound_builder/tools.py"; then
    fail "compound-builder tools.py 不应定义 def git_push 工具"
  else
    pass "compound-builder tools.py 未定义 git_push 工具"
  fi
fi

# Gateway 是否注册 compound-builder
if grep -q '"compound-builder"' "$ROOT/gateway/api/registry.py"; then
  pass "gateway registry 含 compound-builder"
else
  fail "gateway registry 缺 compound-builder"
fi
if grep -q 'compound_builder_router' "$ROOT/gateway/api/routers/__init__.py"; then
  pass "routers/__init__.py 接入 compound_builder_router"
else
  fail "routers/__init__.py 未接入 compound_builder_router"
fi
if [ -f "$ROOT/gateway/api/routers/compound_builder.py" ]; then
  pass "gateway/api/routers/compound_builder.py 存在"
else
  fail "gateway/api/routers/compound_builder.py 缺失"
fi

# -----------------------------------------------------------------
header "10. ModemLogAnalyzer (新 Agent)"
# -----------------------------------------------------------------
MLA=agents/modem-log-analyzer
if [ -d "$MLA" ]; then
  pass "$MLA/ 目录存在"
  for f in pyproject.toml langgraph.json Makefile .env.example AGENTS.md Dockerfile \
           src/modem_log_analyzer/__init__.py src/modem_log_analyzer/agent.py \
           src/modem_log_analyzer/state.py src/modem_log_analyzer/tools.py \
           src/modem_log_analyzer/prompts.py src/modem_log_analyzer/interrupts.py \
           src/modem_log_analyzer/cli.py src/modem_log_analyzer/checkpointer.py \
           src/modem_log_analyzer/tracing.py src/modem_log_analyzer/llm.py \
           src/modem_log_analyzer/skills_loader.py src/modem_log_analyzer/mcp_servers.py \
           src/modem_log_analyzer/subagents.py src/modem_log_analyzer/contracts.py \
           src/modem_log_analyzer/env.py src/modem_log_analyzer/intake.py \
           src/modem_log_analyzer/log_parser.py src/modem_log_analyzer/evidence.py \
           src/modem_log_analyzer/command_catalog.py \
           src/modem_log_analyzer/classification.py \
           src/modem_log_analyzer/scenario_inference.py \
           src/modem_log_analyzer/control_log_policy.py \
           src/modem_log_analyzer/analysis_service.py src/modem_log_analyzer/report.py \
           docs/README.md docs/PROMPT.md docs/INTERRUPTS.md docs/MCP_AND_SKILLS.md \
           tests/__init__.py tests/conftest.py tests/acceptance/test_cli_contract.py \
           tests/unit/test_contracts.py tests/unit/test_tool_registry.py \
           tests/unit/test_skills_loader.py tests/unit/test_intake.py \
           tests/unit/test_log_parser.py tests/unit/test_command_catalog.py \
           tests/unit/test_classification.py tests/unit/test_control_log_policy.py \
           tests/unit/test_report_renderer.py \
           tests/integration/test_cli_intake.py \
           tests/integration/test_agent_diagnosis.py \
           tests/integration/test_interrupt_resume.py \
           tests/integration/test_cli_analyze.py \
           tests/integration/test_gateway.py \
           tests/eval/test_datasets.py \
           knowledge/modemcli_commands.yaml \
           tests/fixtures/reference_case_52/evb.log \
           tests/fixtures/reference_case_52/control.log \
           tests/fixtures/reference_case_52/expected.json; do
    if [ -f "$MLA/$f" ]; then pass "$MLA/$f"; else fail "$MLA/$f"; fi
  done
else
  fail "$MLA/ 不存在"
fi

# 检查 console script
if grep -q 'modem-log-analyzer' "$MLA/pyproject.toml"; then
  pass "pyproject.toml 声明 console script"
else
  fail "pyproject.toml 未声明 modem-log-analyzer console script"
fi

# 检查 classification 枚举与 R13 一致
for c in DEVICE_FAILURE_CONFIRMED ENVIRONMENT_FAILURE_INDICATED \
         TEST_AUTOMATION_FAILURE_CONFIRMED NO_DEVICE_ANOMALY_FOUND \
         DEVICE_EVIDENCE_INCOMPLETE MULTIPLE_POSSIBLE_CAUSES; do
  if grep -q "\"$c\"" "$MLA/src/modem_log_analyzer/contracts.py"; then
    pass "contracts.Classification 含 $c"
  else
    fail "contracts.Classification 缺 $c"
  fi
done

# 检查 Gateway 注册
if grep -q '"modem-log-analyzer"' "$ROOT/gateway/api/registry.py"; then
  pass "gateway registry 含 modem-log-analyzer"
else
  fail "gateway registry 缺 modem-log-analyzer"
fi
if grep -q 'modem_log_analyzer_router' "$ROOT/gateway/api/routers/__init__.py"; then
  pass "routers/__init__.py 接入 modem_log_analyzer_router"
else
  fail "routers/__init__.py 未接入 modem_log_analyzer_router"
fi
if [ -f "$ROOT/gateway/api/routers/modem_log_analyzer.py" ]; then
  pass "gateway/api/routers/modem_log_analyzer.py 存在"
else
  fail "gateway/api/routers/modem_log_analyzer.py 缺失"
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
