"""{{ cookiecutter.agent_pascal }} —— Skills 加载器。

硬规矩 8：禁止任何 Agent 读取 ~/.claude/skills、~/.config/claude、CLAUDE_CODE_SKILLS_DIR
等"用户级 / 全局级"配置。本文件是**项目级**加载器，只接受：

  1. cookiecutter 变量 ``{{ cookiecutter.load_local_skills_dir }}``（默认 ``./skills``），
     路径必须落在项目仓库内，否则拒绝。
  2. cookiecutter 变量 ``{{ cookiecutter.load_skills_from_github }}``（"owner/repo@ref"）。

`load_skill(...)` 工具在运行时被主代理按需调用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# 项目根：用于"路径必须落在项目内"的边界检查。
# cookiecutter 渲染时 `{{ cookiecutter.project_name }}` 已是 "atelier"；
# Agent 实际部署时这里的 PROJECT_ROOT 应解析为仓库根。我们取 cwd 与工作区祖先。
def _project_root() -> Path:
    """回溯寻找含 `pyproject.toml` 的祖先目录。"""
    p = Path(os.getenv("ATELIER_PROJECT_ROOT") or os.getcwd()).resolve()
    for _ in range(8):
        if (p / "pyproject.toml").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path(os.getcwd()).resolve()


PROJECT_ROOT = _project_root()


@dataclass
class SkillSource:
    label: str
    kind: str                                # "dir" | "github"
    location: str                            # 相对/绝对项目内路径 或 "owner/repo@ref"


def _is_inside_project(p: Path) -> bool:
    """拒绝任何项目外的路径（包括 `~/`、全局 `/`、`/Users/.../.../.claude/...` 等）。"""
    try:
        p = p.resolve()
    except RuntimeError:
        return False
    return PROJECT_ROOT in p.parents or p == PROJECT_ROOT


def all_skill_sources() -> list[SkillSource]:
    """返回全部可用 skill 来源，供 SkillsMiddleware 装配。

    严格按硬规矩 8：只接受项目内路径与已声明的 GitHub 仓库。
    """
    out: list[SkillSource] = []

    {% if cookiecutter.load_local_skills_dir != "none" %}
    local_raw = "{{ cookiecutter.load_local_skills_dir }}"
    if local_raw:
        local = (PROJECT_ROOT / local_raw).resolve() if not Path(local_raw).is_absolute() \
                else Path(local_raw).resolve()
        # 反向断言：绝对禁止 ~/.claude/skills、CLAUDE_CODE_SKILLS_DIR 等全局路径
        forbidden_substrings = (
            ".claude/skills", ".claude\\skills",
            "CLAUDE_CODE_SKILLS_DIR",
        )
        s = str(local)
        if any(fs in s for fs in forbidden_substrings):
            raise RuntimeError(
                f"REFUSED: local skills path '{local}' looks like a global Claude config. "
                "Atelier AGENTS.md rule #8: project-level only."
            )
        if not _is_inside_project(local):
            raise RuntimeError(
                f"REFUSED: local skills path '{local}' is outside the project "
                f"root '{PROJECT_ROOT}'. Atelier AGENTS.md rule #8."
            )
        if local.exists():
            out.append(SkillSource(label="local", kind="dir", location=str(local)))
    {% endif %}

    {% if cookiecutter.load_skills_from_github != "none" %}
    gh = "{{ cookiecutter.load_skills_from_github }}"
    if gh and "@" in gh or (gh and "/" in gh):
        out.append(SkillSource(label="github", kind="github", location=gh))
    {% endif %}

    return out


def to_deepagents_source(s: SkillSource) -> dict:
    """转成 deepagents SkillsMiddleware 能吃的格式。"""
    if s.kind == "dir":
        return {"type": "directory", "path": s.location}
    if s.kind == "github":
        if "@" in s.location:
            repo, ref = s.location.split("@", 1)
            return {"type": "github", "repo": repo, "ref": ref}
        return {"type": "github", "repo": s.location, "ref": "main"}
    raise ValueError(f"unknown skill source kind: {s.kind}")
