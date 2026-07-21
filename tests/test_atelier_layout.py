"""Atelier 顶层测试:仅检查结构,不依赖任何第三方库。

启动:
    cd atelier && pytest -q tests/
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_root_files_exist():
    for f in (
        "README.md", "AGENTS.md", "CLAUDE.md", "Makefile",
        "pyproject.toml", ".gitignore", ".env.example",
        "scripts/smoke.sh",
    ):
        assert (ROOT / f).exists(), f"missing root file: {f}"


def test_template_dir_exists():
    tdir = ROOT / "_templates" / "agent-template"
    assert tdir.exists()
    assert (tdir / "cookiecutter.json").exists()


def test_example_agent_exists():
    cwd = ROOT / "agents" / "code-writer"
    assert cwd.exists()
    assert (cwd / "src/code_writer/agent.py").exists()
    assert (cwd / "langgraph.json").exists()
    assert (cwd / "Makefile").exists()


def test_agent_dirs_use_hyphen_not_underscore():
    """Agent 目录 slug 必须用连字符 (modem-log-analyzer), 禁止下划线目录名。

    Python import 包名可以是 underscore (modem_log_analyzer), 但 agents/<slug>/
    约定与 gateway registry 一致, 一律 hyphen。曾误留 agents/modem-log_analyzer/
    与完整包并存, 用本断言防回归。
    """
    agents_root = ROOT / "agents"
    assert agents_root.is_dir()
    bad = sorted(
        p.name for p in agents_root.iterdir() if p.is_dir() and "_" in p.name
    )
    assert bad == [], (
        f"agents/ 下禁止含下划线的目录 (应用 hyphen): {bad}"
    )


def test_example_agent_no_push_in_tools():
    """git_push / shell_push 不能作为工具注册到 main agent。

    静态检查:不在顶层测试运行时 import tools(顶层 venv 可能没装所有
    Agent 依赖);改用 grep tools.py 源文件 + 比对 ``def git_push`` 等模式。
    """
    tools = ROOT / "agents/code-writer/src/code_writer/tools.py"
    assert tools.exists()
    txt = tools.read_text()
    # 反向断言
    for forbidden in ("git_push_tool", '"git_push"', "def git_push"):
        assert forbidden not in txt, f"tools.py 仍含禁用声明 {forbidden}"


def test_gateway_layout():
    g = ROOT / "gateway/api"
    assert g.exists()
    assert (g / "main.py").exists()
    assert (g / "routers/code_writer.py").exists()


def test_subagent_default_three():
    txt = (ROOT / "agents/code-writer/src/code_writer/subagents.py").read_text()
    for name in ("researcher", "tester", "reviewer"):
        assert f'name="{name}"' in txt


# ============================================================
# Compound Builder 接入测试(plan R21)
# ============================================================
def test_compound_builder_layout():
    cb = ROOT / "agents" / "compound-builder"
    assert cb.exists()
    assert (cb / "src/compound_builder/agent.py").exists()
    assert (cb / "src/compound_builder/graph.py").exists()
    assert (cb / "src/compound_builder/state.py").exists()
    assert (cb / "langgraph.json").exists()
    assert (cb / "Makefile").exists()

    # 10 节点(nodes/*.py)
    nodes_dir = cb / "src/compound_builder/nodes"
    for name in (
        "coordinator.py", "executor.py", "validator.py", "fixer.py",
        "review_coordinator.py", "dimension_reviewer.py",
        "review_synthesizer.py", "shipper.py", "reporter.py",
        "progress_steward.py",
    ):
        assert (nodes_dir / name).exists(), f"missing node: {name}"


def test_compound_builder_no_push_in_tools():
    """R9:git_push 类工具绝不能注册。

    静态检查 vs docstring 反向断言(后者的 `\"git_push\"` 是合法警告字符串)。
    """
    tools = ROOT / "agents/compound-builder/src/compound_builder/tools.py"
    assert tools.exists()
    txt = tools.read_text()
    # 真注册会用 @tool 包 def git_push(...),或 import 时 name="git_push"
    assert not re.search(r"@tool[\s\S]{0,200}?def\s+git_push(?:_tool)?\s*\(", txt), \
        "tools.py 含 @tool 装饰的 def git_push"
    assert not re.search(r"name\s*=\s*[\"']git_push[\"']", txt), \
        "tools.py 仍有 name='git_push' 的工具"
    # 反向断言:_assert_no_push 必须存在(本文件 self-check)
    assert "_assert_no_push" in txt, "tools.py 缺少 _assert_no_push 反向断言"


def test_compound_builder_no_push_in_static_analysis():
    """静态 grep compound-builder 源码,找出**任何** ``def git_push(...)`` 函数定义
    或 ``@tool`` 装饰的 git_push。注意:docstring 中的 ``"git_push"`` 是允许的
    (反向断言本来就会显示禁用字符串)。"""
    cb = ROOT / "agents/compound-builder/src/compound_builder"
    found = []
    for py in cb.rglob("*.py"):
        text = py.read_text()
        # 真正会注册成 LangChain 工具的代码模式
        if re.search(r"@tool[\s\S]{0,200}?def\s+git_push\b", text):
            found.append(str(py.relative_to(ROOT)))
        if re.search(r"def\s+git_push(?:_tool)?\s*\(", text):
            found.append(str(py.relative_to(ROOT)))
    assert not found, f"compound-builder 源码仍含 git_push 工具定义: {found}"


def test_compound_builder_registered_in_gateway():
    """R15:gateway registry 必须含 compound-builder。"""
    text = (ROOT / "gateway/api/registry.py").read_text()
    assert '"compound-builder"' in text
    assert "Compound Builder" in text


def test_compound_builder_routes_registered():
    """R16/R17:compound_builder_router 必须注册到 ALL_ROUTERS。"""
    init_text = (ROOT / "gateway/api/routers/__init__.py").read_text()
    assert "compound_builder_router" in init_text
    assert (ROOT / "gateway/api/routers/compound_builder.py").exists()


# ============================================================
# ModemLogAnalyzer 接入测试(Unit 1)
# ============================================================
def test_modem_log_analyzer_layout():
    """Unit 1 验收: agents/modem-log-analyzer/ 骨架完整。"""
    ma = ROOT / "agents" / "modem-log-analyzer"
    assert ma.exists()
    assert (ma / "pyproject.toml").exists()
    assert (ma / "langgraph.json").exists()
    assert (ma / "Makefile").exists()
    assert (ma / ".env.example").exists()
    assert (ma / "AGENTS.md").exists()
    assert (ma / "Dockerfile").exists()

    # src/modem_log_analyzer 必填骨架
    src = ma / "src" / "modem_log_analyzer"
    for fname in (
        "__init__.py",
        "contracts.py",
        "cli.py",
        "agent.py",
        "state.py",
        "subagents.py",
        "prompts.py",
        "tools.py",
        "interrupts.py",
        "checkpointer.py",
        "tracing.py",
        "skills_loader.py",
        "mcp_servers.py",
        "llm.py",
        "env.py",
        "analysis_service.py",
    ):
        assert (src / fname).exists(), f"missing: src/modem_log_analyzer/{fname}"

    # docs
    for d in ("README.md", "PROMPT.md", "MCP_AND_SKILLS.md", "INTERRUPTS.md"):
        assert (ma / "docs" / d).exists(), f"missing: docs/{d}"

    # tests
    for t in (
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/unit/test_contracts.py",
        "tests/unit/test_tool_registry.py",
        "tests/unit/test_skills_loader.py",
        "tests/acceptance/test_cli_contract.py",
    ):
        assert (ma / t).exists(), f"missing: {t}"


def test_modem_log_analyzer_no_dangerous_tools():
    """Unit 1: tools.py 不暴露 bash / git_push / 通用 write_file / git_commit。

    注意:docstring / 反向断言字符串(如 ``"def git_push"``)是允许的;
    只检查真正的函数定义与 ``@tool`` 装饰。
    """
    tools = ROOT / "agents/modem-log-analyzer/src/modem_log_analyzer/tools.py"
    assert tools.exists()
    txt = tools.read_text()
    # 真注册会写成 ``def git_push(``(后接参数)或被 ``@tool`` 装饰。
    import re as _re
    for forbidden in ("git_push", "bash_tool", "write_file_tool", "git_commit_tool"):
        # 真实函数定义: ``def <name>(`` 前可有空格, 不可在字符串字面量上下文里。
        # 用多行扫描:匹配 ``def forbidden(`` 排除字符串上下文。
        pat = rf"^\s*def\s+{_re.escape(forbidden)}\s*\("
        for ln, line in enumerate(txt.splitlines(), 1):
            if _re.search(pat, line):
                raise AssertionError(
                    f"tools.py:LINE {ln} 含禁用函数定义 `{line.strip()}`"
                )


def test_modem_log_analyzer_no_global_skill_load():
    """Unit 1: skills_loader 不得读取 ~/.claude/skills / CLAUDE_CODE_SKILLS_DIR。"""
    sl = ROOT / "agents/modem-log-analyzer/src/modem_log_analyzer/skills_loader.py"
    assert sl.exists()
    txt = sl.read_text()
    assert "_assert_project_local" in txt, "缺少项目级边界检查"
    # 反向断言字符串必须存在,且配合禁用关键字使用
    assert ".claude/skills" in txt or "CLAUDE_CODE_SKILLS_DIR" in txt
    # 真正的"读 ~/.claude"路径不允许出现
    assert 'Path.home() / ".claude"' not in txt


def test_modem_log_analyzer_console_script_declared():
    """Unit 1: pyproject.toml 必须声明 console script ``modem-log-analyzer``。"""
    pyproject = ROOT / "agents/modem-log-analyzer/pyproject.toml"
    txt = pyproject.read_text()
    assert "modem-log-analyzer" in txt
    assert "modem_log_analyzer.cli:cli" in txt


def test_modem_log_analyzer_classification_enum_matches_r13():
    """Unit 1: contracts.Classification 必须严格匹配需求 R13 的 6 个值。"""
    contracts = ROOT / "agents/modem-log-analyzer/src/modem_log_analyzer/contracts.py"
    txt = contracts.read_text()
    expected = {
        "DEVICE_FAILURE_CONFIRMED",
        "ENVIRONMENT_FAILURE_INDICATED",
        "TEST_AUTOMATION_FAILURE_CONFIRMED",
        "NO_DEVICE_ANOMALY_FOUND",
        "DEVICE_EVIDENCE_INCOMPLETE",
        "MULTIPLE_POSSIBLE_CAUSES",
    }
    for v in expected:
        assert f'"{v}"' in txt, f"Classification 缺 {v}"


# ============================================================
# ModemLogAnalyzer Gateway 接入 (Unit 8)
# ============================================================
def test_modem_log_analyzer_in_gateway_registry():
    """gateway registry 必须包含 modem-log-analyzer (Unit 8)。"""
    txt = (ROOT / "gateway/api/registry.py").read_text(encoding="utf-8")
    assert '"modem-log-analyzer"' in txt
    assert "modem_log_analyzer.agent" in txt


def test_modem_log_analyzer_router_registered():
    """routers/__init__.py 必须接入 modem_log_analyzer_router。"""
    init_text = (ROOT / "gateway/api/routers/__init__.py").read_text()
    assert "modem_log_analyzer_router" in init_text
    assert (ROOT / "gateway/api/routers/modem_log_analyzer.py").exists()


def test_modem_log_analyzer_report_renderer_exists():
    """Unit 6: report renderer 必须存在。"""
    src = ROOT / "agents/modem-log-analyzer/src/modem_log_analyzer/report.py"
    assert src.exists()
    txt = src.read_text()
    # 章节顺序必须锁定
    for section in [
        "失败概览",
        "推断的测试场景与基线",
        "核心诊断",
        "根因链",
        "失败时间线",
        "测试步骤与日志证据",
        "故障域判定与推理",
        "剩余不确定性",
        "建议行动",
        "正式证据索引",
    ]:
        assert section in txt, f"renderer 缺章节: {section}"


def test_modem_log_analyzer_control_log_policy_exists():
    """Unit 5: control_log_policy 必须存在并含关键函数。"""
    src = ROOT / "agents/modem-log-analyzer/src/modem_log_analyzer/control_log_policy.py"
    assert src.exists()
    txt = src.read_text()
    for fn in [
        "should_request_control_log",
        "has_direct_automation_evidence",
        "finalize_classification_after_user_choice",
        "build_resume_payload",
        "build_interrupt_request",
    ]:
        assert fn in txt, f"control_log_policy 缺函数: {fn}"


def test_modem_log_analyzer_test_datasets_exist():
    """Unit 7: 风险驱动测试 + reference_case_52 fixture 必须存在。"""
    assert (ROOT / "agents/modem-log-analyzer/tests/eval/test_datasets.py").exists()
    fx = ROOT / "agents/modem-log-analyzer/tests/fixtures/reference_case_52"
    assert (fx / "evb.log").exists()
    assert (fx / "control.log").exists()
    assert (fx / "expected.json").exists()
    # fixture 数据必须脱敏 (不应有真实电话号码 / 长数字串)
    evb_text = (fx / "evb.log").read_text()
    import re as _re

    phone = _re.search(r"\b1[3-9]\d{9}\b", evb_text)
    assert phone is None, f"reference_case_52/evb.log 含未脱敏的电话: {phone}"
    long = _re.search(r"\b\d{10,}\b", evb_text.replace("2026-07-19", "").replace("000000000", ""))
    # 允许日期内的数字串; 拒绝真正长串
    assert long is None, "reference_case_52/evb.log 含可疑长数字串"
