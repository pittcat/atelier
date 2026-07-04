"""Code Writer —— Skills 加载器（项目级，硬规矩 8）。

Sources（按声明顺序）：
  1. 本地 ./skills/
  2. cookiecutter / 环境变量声明的 GitHub 仓库

**绝不**读取 ~/.claude/skills、CLAUDE_CODE_SKILLS_DIR 等全局路径。
任何指向项目外的路径都会被显式拒绝。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SkillSource:
    label: str
    kind: str           # "dir" | "github"
    location: str


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


def _is_inside_project(p: Path) -> bool:
    try:
        p = p.resolve()
    except RuntimeError:
        return False
    return PROJECT_ROOT in p.parents or p == PROJECT_ROOT


def _assert_project_local(path: Path) -> None:
    """硬规矩 8：拒绝任何项目外路径与已知全局配置位置。"""
    s = str(path)
    forbidden_substrings = (
        ".claude/skills", ".claude\\skills",
        "CLAUDE_CODE_SKILLS_DIR",
        "/.config/claude/",
    )
    if any(fs in s for fs in forbidden_substrings):
        raise RuntimeError(
            f"REFUSED: skill path '{s}' references a global Claude config. "
            "Atelier AGENTS.md rule #8: project-level only."
        )
    if not _is_inside_project(path):
        raise RuntimeError(
            f"REFUSED: skill path '{path}' is outside project root "
            f"'{PROJECT_ROOT}'. Atelier AGENTS.md rule #8."
        )


def _local_dir() -> Optional[Path]:
    """解析本地项目级 skills 目录。"""
    raw = os.getenv("ATELIER_LOCAL_SKILLS_DIR", "skills").strip()
    if not raw or raw == "none":
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (PROJECT_ROOT / raw).resolve()
    _assert_project_local(p)
    return p if p.exists() else None


def _github_source() -> Optional[str]:
    """从 env 取 GitHub skill 仓库（"owner/repo@ref"）。"""
    return os.getenv("ATELIER_SKILLS_GITHUB") or None


def all_skill_sources() -> list[SkillSource]:
    out: list[SkillSource] = []

    local = _local_dir()
    if local is not None:
        out.append(SkillSource(label="local", kind="dir", location=str(local)))

    gh = _github_source()
    if gh:
        out.append(SkillSource(label="github", kind="github", location=gh))

    return out


def to_deepagents_source(s: SkillSource) -> dict:
    if s.kind == "dir":
        return {"type": "directory", "path": s.location}
    if s.kind == "github":
        if "@" in s.location:
            repo, ref = s.location.split("@", 1)
            return {"type": "github", "repo": repo, "ref": ref}
        return {"type": "github", "repo": s.location, "ref": "main"}
    raise ValueError(s.kind)


if __name__ == "__main__":
    import json
    print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))
