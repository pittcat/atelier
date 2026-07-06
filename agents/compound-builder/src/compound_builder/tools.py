"""CompoundBuilder —— 工具集。

按 plan R8 / R9 / R11:
  - 工具集合包含 R8 列出的全部工具。
  - 严格不导出任何 push 类工具(走 _assert_no_push 反向断言)。
  - ``discover_test_entry`` 用优先级链(R11)。
  - ``parse_plan`` / ``validate_plan`` 用 Pydantic 强校验(R7)。

本文件用纯 stdlib + pydantic + langchain_core.tool,无外部网络依赖,
便于 UI / 测试时直接调用。
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Annotated, Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field, ValidationError

from compound_builder.workdir_ctx import get_workdir, resolve_path


# ============================================================
# Pydantic schemas (R5-R7)
# ============================================================
class UnitSchema(BaseModel):
    id: str
    title: str
    files: list[str] = Field(default_factory=list)
    approach: str = ""
    test_scenarios: list[str] = Field(default_factory=list)
    verification: str = ""


class PlanSchema(BaseModel):
    title: str
    acceptance: list[str] = Field(default_factory=list)
    scope_boundaries: list[str] = Field(default_factory=list)
    units: list[UnitSchema] = Field(min_length=1)


class PlanValidationError(ValueError):
    """plan 校验失败 → coordinator 升级 plan.blocked(R7)。"""


# ============================================================
# 异常
# ============================================================
class NoTestEntryError(RuntimeError):
    """discover_test_entry 落空时抛(R11)→ coordinator 升级 plan.blocked。"""


# ============================================================
# 文件与 shell 类工具(R8)
# ============================================================
@tool
def read_file(path: str) -> str:
    """读取文件内容。path 相对于当前 workdir(见 ATELIER_WORKDIR / state.workdir)。"""
    p = resolve_path(path)
    if not p.exists():
        return f"[read_file] not found: {path}"
    return p.read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """写文件。新建 / 覆盖。"""
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"[write_file] wrote {len(content)} bytes to {path}"


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """把文件中 old_string 替换为 new_string。old_string 必须唯一。"""
    p = resolve_path(path)
    if not p.exists():
        return f"[edit_file] not found: {path}"
    text = p.read_text(encoding="utf-8")
    n = text.count(old_string)
    if n != 1:
        return f"[edit_file] expected 1 occurrence of old_string, found {n}"
    new_text = text.replace(old_string, new_string, 1)
    p.write_text(new_text, encoding="utf-8")
    return f"[edit_file] patched {path}"


@tool
def glob(pattern: str) -> list[str]:
    """在 workdir 下执行 glob,返回相对 workdir 的路径列表。"""
    root = get_workdir()
    return sorted(str(p.relative_to(root)) for p in root.glob(pattern))


@tool
def grep(pattern: str, path: str = ".") -> list[str]:
    """在 workdir 下搜文本,返回匹配行(file:line:content)。"""
    out: list[str] = []
    pat = re.compile(pattern)
    root = get_workdir()
    base = resolve_path(path)
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
                if pat.search(line):
                    try:
                        rel = p.relative_to(root)
                    except ValueError:
                        rel = p
                    out.append(f"{rel}:{i}:{line}")
        except (UnicodeDecodeError, OSError):
            continue
    return out


@tool
def bash(command: str, timeout: int = 120) -> str:
    """在 workdir 下执行 shell 命令(支持 ``cd sub && pytest`` 等复合命令)。"""
    if not command.strip():
        return "[bash] empty command"
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=get_workdir(),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return f"[bash] timeout after {timeout}s: {e}"
    out = proc.stdout
    err = proc.stderr
    return f"[bash exit={proc.returncode}]\nstdout:\n{out}\nstderr:\n{err}"


# ============================================================
# Git 类工具 — 注意:绝对不导出 push 类
# ============================================================
def _git(*args: str) -> str:
    """Run a git command (no push ever) in workdir."""
    proc = subprocess.run(
        ["git", *args],
        cwd=get_workdir(),
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "") + (proc.stderr or "")


@tool
def git_status() -> str:
    """``git status``。"""
    return _git("status", "--short")


@tool
def git_diff(path: str = "") -> str:
    """``git diff``(可选 path 过滤)。"""
    args = ["diff"]
    if path:
        args.append(path)
    return _git(*args)


@tool
def git_commit(message: str, paths: list[str] | None = None) -> str:
    """``git add`` 后 ``git commit -m <msg>``。paths 为空时 ``git add -A``。"""
    if paths:
        add_out = _git("add", "--", *paths)
    else:
        add_out = _git("add", "-A")
    commit_out = _git("commit", "-m", message)
    return f"[git add]\n{add_out}\n[git commit]\n{commit_out}"


# NOTE: 故意不导出任何 push 类工具。具体名单见 _assert_no_push 的 banned_substrings。
# 任何审查 smoke.sh 段 9 会 grep 相关模式,确保 0 命中。


# ============================================================
# Plan 校验 / 解析(R7)
# ============================================================
@tool
def parse_plan(plan_path: str) -> dict:
    """解析 plan.md,返回 ``{title, acceptance, scope_boundaries, units}``。

    用简化的 markdown 解析:
      - YAML frontmatter ``title:`` 或第一段 ``#`` 头视为 title。
      - ``- [ ]`` / ``- [x]`` 行视为 unit(``step-NN`` ID 自增生成)。
      - ``## Implementation Units`` + ``#### stepN.`` 块(Ralph / ce-plan 格式)。
      - ``## Acceptance`` / ``## Requirements`` 后的列表视为 acceptance。
      - ``## Scope Boundaries`` → ``### In Scope`` 视为 scope_boundaries。
    """
    return _parse_plan(Path(plan_path))


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL | re.MULTILINE)
_STEP_HEAD_RE = re.compile(r"^####\s+step\s*(\d+)\.\s*(.+)$", re.IGNORECASE)
_FIELD_RE = re.compile(
    r"^\s*-\s+\*\*(Goal|Files|Approach|Test scenarios|Verification|Execution note):\*\*\s*(.*)$",
    re.IGNORECASE,
)
_FILE_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _parse_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, {}
    meta: dict[str, str] = {}
    for raw in m.group(1).splitlines():
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        meta[key.strip()] = val.strip()
    return text[m.end() :], meta


def _split_file_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    found = _FILE_BACKTICK_RE.findall(raw)
    if found:
        return [f.strip() for f in found if f.strip()]
    return [p.strip() for p in raw.split(",") if p.strip()]


def _section_slice(lines: list[str], heading: str) -> list[str]:
    """Extract lines under ``## <heading>`` until the next ``## ``."""
    pat = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.IGNORECASE)
    start: int | None = None
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i + 1
            break
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start:]:
        if re.match(r"^##\s+", line):
            break
        out.append(line)
    return out


def _parse_implementation_units(lines: list[str]) -> list[dict]:
    """Ralph / ce-plan 格式:``## Implementation Units`` + ``#### stepN.`` 块。"""
    block = _section_slice(lines, "Implementation Units")
    if not block:
        return []

    units: list[dict] = []
    current: dict[str, Any] | None = None
    active_field: str | None = None

    def _flush() -> None:
        nonlocal current
        if current is None:
            return
        goal = current.pop("_goal", "")
        if goal and not current.get("approach"):
            current["approach"] = goal
        elif goal:
            current["approach"] = f"{goal}\n{current['approach']}".strip()
        units.append(current)
        current = None

    for line in block:
        m_step = _STEP_HEAD_RE.match(line)
        if m_step:
            _flush()
            current = {
                "id": f"step-{int(m_step.group(1)):02d}",
                "title": m_step.group(2).strip(),
                "files": [],
                "approach": "",
                "test_scenarios": [],
                "verification": "",
            }
            active_field = None
            continue
        if current is None:
            continue

        m_field = _FIELD_RE.match(line)
        if m_field:
            name = m_field.group(1).lower()
            rest = m_field.group(2).strip()
            if name == "goal":
                current["_goal"] = rest
                active_field = None
            elif name == "files":
                current["files"] = _split_file_list(rest)
                active_field = None
            elif name == "approach":
                current["approach"] = rest
                active_field = "approach"
            elif name == "test scenarios":
                active_field = "test_scenarios"
                if rest:
                    current["test_scenarios"].append(rest)
            elif name == "verification":
                current["verification"] = rest.strip("`").strip()
                active_field = None
            else:
                active_field = None
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if active_field == "approach" and stripped.startswith("- "):
            part = stripped[2:].strip()
            sep = "\n" if current["approach"] else ""
            current["approach"] = f"{current['approach']}{sep}- {part}"
        elif active_field == "test_scenarios" and stripped.startswith("- "):
            current["test_scenarios"].append(stripped[2:].strip())

    _flush()

    # 多个 UNIT 可能都叫 step1 —— 按出现顺序重编号
    for i, unit in enumerate(units, start=1):
        unit["id"] = f"step-{i:02d}"
    return units


def _parse_plan(path: Path) -> dict:
    raw_text = path.read_text(encoding="utf-8")
    body, frontmatter = _parse_frontmatter(raw_text)
    lines = body.splitlines()
    title = frontmatter.get("title", "")
    units: list[dict] = []
    acceptance: list[str] = []
    scope: list[str] = []

    section: str | None = None
    scope_sub: str | None = None
    bullet_re = re.compile(r"^\s*-\s+\[\s*[xX ]\s*\]\s+(.*)$")
    head_re = re.compile(r"^#\s+(.*)$")
    sub_re = re.compile(r"^##\s+(.*)$")
    h3_re = re.compile(r"^###\s+(.*)$")

    for line in lines:
        m_sub = sub_re.match(line)
        if m_sub:
            heading = m_sub.group(1).strip().lower()
            scope_sub = None
            if "acceptance" in heading:
                section = "acceptance"
            elif heading == "requirements":
                section = "requirements"
            elif "scope" in heading:
                section = "scope"
            else:
                section = None
            continue
        m_h3 = h3_re.match(line)
        if m_h3 and section == "scope":
            h3 = m_h3.group(1).strip().lower()
            scope_sub = "in_scope" if "in scope" in h3 else None
            continue
        m_head = head_re.match(line)
        if m_head and not title:
            title = m_head.group(1).strip()
            section = None
            continue
        m_bul = bullet_re.match(line)
        if m_bul:
            content = m_bul.group(1).strip()
            if section == "acceptance":
                acceptance.append(content)
            elif section == "requirements":
                acceptance.append(content)
            elif section == "scope":
                # checkbox 单元出现在 scope 段之后(旧格式无 ### In Scope)
                section = None
                idx = len(units) + 1
                units.append(
                    {
                        "id": f"step-{idx:02d}",
                        "title": content,
                        "files": [],
                        "approach": "",
                        "test_scenarios": [],
                        "verification": "",
                    }
                )
            else:
                idx = len(units) + 1
                units.append(
                    {
                        "id": f"step-{idx:02d}",
                        "title": content,
                        "files": [],
                        "approach": "",
                        "test_scenarios": [],
                        "verification": "",
                    }
                )
            continue
        if section in ("acceptance", "requirements") and line.startswith("- "):
            acceptance.append(line[2:].strip())
        elif section == "scope" and scope_sub == "in_scope" and line.startswith("- "):
            scope.append(line[2:].strip())
        elif section == "scope" and scope_sub is None and line.startswith("- "):
            scope.append(line[2:].strip())
        elif not line.strip():
            if section not in ("acceptance", "requirements", "scope"):
                section = None

    if not units:
        units = _parse_implementation_units(lines)

    if not acceptance:
        for item in _section_slice(lines, "Requirements"):
            s = item.strip()
            if s.startswith("- "):
                acceptance.append(s[2:].strip())

    try:
        schema = PlanSchema(
            title=title or "(untitled)",
            acceptance=acceptance,
            scope_boundaries=scope,
            units=[UnitSchema(**u) for u in units],
        )
    except ValidationError as e:
        raise PlanValidationError(str(e)) from e

    return schema.model_dump()


@tool
def validate_plan(plan_dict: dict) -> dict:
    """验证 plan_dict 是否符合 PlanSchema。返回 ``{"ok": bool, "errors": [...]}``。"""
    try:
        PlanSchema(**plan_dict)
    except ValidationError as e:
        return {"ok": False, "errors": e.errors()}
    return {"ok": True, "errors": []}


# ============================================================
# 测试入口自发现(R11 / KTD-5)
# ============================================================
_DISCOVER_ERROR_PREFIX = "[discover_test_entry] error:"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _pytest_cmd_for_dir(directory: Path, *, root: Path) -> str | None:
    """若 directory 像 pytest 项目,返回可执行的 pytest 命令(含必要 cd)。"""
    pyproject = directory / "pyproject.toml"
    if pyproject.exists():
        text = _read_text(pyproject)
        if "[tool.pytest]" in text or "pytest" in text:
            if directory.resolve() == root.resolve():
                return "pytest -v"
            rel = directory.relative_to(root).as_posix()
            return f"cd {rel} && pytest -v"
    if (directory / "pytest.ini").exists():
        if directory.resolve() == root.resolve():
            return "pytest -v"
        rel = directory.relative_to(root).as_posix()
        return f"cd {rel} && pytest -v"
    if (directory / "setup.cfg").exists() and "[tool:pytest]" in _read_text(directory / "setup.cfg"):
        if directory.resolve() == root.resolve():
            return "pytest -v"
        rel = directory.relative_to(root).as_posix()
        return f"cd {rel} && pytest -v"
    tests_dir = directory / "tests"
    if tests_dir.is_dir() and any(tests_dir.rglob("test_*.py")):
        if directory.resolve() == root.resolve():
            return "pytest -v"
        rel = directory.relative_to(root).as_posix()
        return f"cd {rel} && pytest -v"
    return None


def discover_test_entry_impl(workdir: str = ".") -> str | None:
    """按优先级链发现测试入口;未找到返回 ``None``。"""
    root = Path(workdir).resolve()

    hit = _pytest_cmd_for_dir(root, root=root)
    if hit:
        return hit

    makefile = root / "Makefile"
    if makefile.exists() and re.search(r"^test:", _read_text(makefile), re.MULTILINE):
        return "make test"

    if (root / "Cargo.toml").exists():
        return "cargo test --workspace"

    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(_read_text(pkg_json))
        except json.JSONDecodeError:
            pkg = {}
        if "test" in pkg.get("scripts", {}):
            return "npm test"

    if (root / "go.mod").exists():
        return "go test ./..."

    # 单子目录包(如 ralph-e2e/sorts/)
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in {"node_modules", "venv", ".venv", "dist", "build", "__pycache__"}:
            continue
        hit = _pytest_cmd_for_dir(child, root=root)
        if hit:
            return hit

    if list(root.rglob("test_*.py"))[:1]:
        return "pytest -v"

    return None


def discover_test_entry_or_raise(workdir: str = ".") -> str:
    """编程式调用;未找到时抛 ``NoTestEntryError``。"""
    cmd = discover_test_entry_impl(workdir)
    if cmd is None:
        raise NoTestEntryError(f"no test entry discovered under {workdir}")
    return cmd


@tool
def discover_test_entry(workdir: str = ".") -> str:
    """按优先级链发现测试入口命令。未找到时返回错误文本(不抛异常,避免 agent 崩溃)。"""
    cmd = discover_test_entry_impl(workdir)
    if cmd is None:
        return f"{_DISCOVER_ERROR_PREFIX} no test entry discovered under {workdir}"
    return cmd


@tool
def run_tests(entry: str | None = None, workdir: str = ".") -> str:
    """自发现 test entry 并跑测试,返回 stdout/stderr 摘要。"""
    if entry:
        cmd = entry
    else:
        discovered = discover_test_entry_impl(workdir)
        if discovered is None:
            return json.dumps(
                {
                    "entry": "",
                    "returncode": 1,
                    "stdout_tail": "",
                    "stderr_tail": f"{_DISCOVER_ERROR_PREFIX} no test entry under {workdir}",
                },
                ensure_ascii=False,
            )
        cmd = discovered

    # ``cd pkg && pytest`` 需要在 shell 中执行
    if "&&" in cmd or "|" in cmd or ";" in cmd:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    else:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=workdir,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    return json.dumps(
        {
            "entry": cmd,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        },
        ensure_ascii=False,
    )


# ============================================================
# Findings / state events(R8)
# ============================================================
@tool
def write_findings_json(findings: list[dict], path: str) -> str:
    """把 review findings 写到 json 文件,供 shipper / 上层查看。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"[write_findings_json] {len(findings)} → {path}"


@tool
def emit_state_event(event: str, payload: dict | None = None) -> str:
    """记录一个 state event;返回 JSON 摘要(便于 trace)。"""
    return json.dumps({"event": event, "payload": payload or {}}, ensure_ascii=False)


# ============================================================
# build_tools — 主入口
# ============================================================
def build_tools() -> list[BaseTool]:
    tools: list[BaseTool] = [
        read_file,
        write_file,
        edit_file,
        glob,
        grep,
        bash,
        git_status,
        git_diff,
        git_commit,
        parse_plan,
        validate_plan,
        discover_test_entry,
        run_tests,
        write_findings_json,
        emit_state_event,
    ]
    # 反向断言:严格不导出任何 push 类
    _assert_no_push(tools)
    return tools


def _assert_no_push(tools: list[BaseTool]) -> None:
    """Build-time reverse-assert:严禁导出 push 类工具。

    检查两层:
      1. **工具名** — ``t.name`` 不能含 push-style 子串。
      2. **模块顶层函数定义** — push-style 函数不能出现在本模块(覆盖
         ``@tool`` 装饰已剥离 / 尚未应用的"半生"代码)。

    任一触发抛 ``RuntimeError``(Build-time fail-fast)。
    """
    banned_substrings = ("git_push", "git_push_tool", "git_worktree_add")
    for t in tools:
        n = (getattr(t, "name", "") or "") + ""
        if any(b in n for b in banned_substrings):
            raise RuntimeError(
                f"REFUSED: push-like tool '{n}' cannot be in build_tools()(AGENTS.md #2)."
            )
    import re
    import inspect
    try:
        src = inspect.getsource(inspect.getmodule(_assert_no_push)) or ""
    except (OSError, TypeError):
        return
    for m in re.finditer(r"^def\s+(git_push(?:_tool|)\b)", src, re.MULTILINE):
        raise RuntimeError(
            f"REFUSED: def {m.group(1)} defined in tools.py"
            "(AGENTS.md #2 forbids any push-like tool definition)."
        )


__all__ = [
    "build_tools",
    "PlanSchema",
    "PlanValidationError",
    "NoTestEntryError",
    "UnitSchema",
]
