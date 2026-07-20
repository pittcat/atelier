"""ModemLogAnalyzer —— Skills 加载器。

硬规矩 8：禁止任何 Agent 读取 ~/.claude/skills、~/.config/claude、CLAUDE_CODE_SKILLS_DIR
等"用户级 / 全局级"配置。本文件是**项目级**加载器，只接受：

  1. cookiecutter 变量 ``./skills``（默认 ``./skills``），
     路径必须落在项目仓库内，否则拒绝。
  2. cookiecutter 变量 ``none``（"owner/repo@ref"）。

`load_skill(...)` 工具在运行时被主代理按需调用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    """回溯寻找含 ``pyproject.toml`` 的祖先目录。"""
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
    kind: str  # "dir" | "github"
    location: str  # 相对/绝对项目内路径 或 "owner/repo@ref"


# 硬规矩 8: 全局配置相关的禁用子串。
# 任何指向这些位置的路径必须在反向断言里出现,不能用于加载 skill。
_FORBIDDEN_SUBSTRINGS = (
    ".claude/skills",
    ".claude\\skills",
    "CLAUDE_CODE_SKILLS_DIR",
)


def _is_inside_project(p: Path) -> bool:
    """拒绝任何项目外的路径（包括 ``~/``、全局 ``/``、``/Users/.../.claude/...`` 等）。"""
    try:
        p = p.resolve()
    except RuntimeError:
        return False
    return PROJECT_ROOT in p.parents or p == PROJECT_ROOT


def _assert_project_local(path: Path) -> None:
    """硬规矩 8：拒绝任何项目外路径与已知全局配置位置。

    raises:
        RuntimeError: 当路径指向全局 Claude 配置或项目外时。
    """
    s = str(path)
    if any(fs in s for fs in _FORBIDDEN_SUBSTRINGS):
        raise RuntimeError(
            f"REFUSED: skill path '{s}' references a global Claude config. "
            "Atelier AGENTS.md rule #8: project-level only."
        )
    if not _is_inside_project(path):
        raise RuntimeError(
            f"REFUSED: skill path '{path}' is outside project root "
            f"'{PROJECT_ROOT}'. Atelier AGENTS.md rule #8."
        )


def _local_dir() -> Path | None:
    """解析本地项目级 skills 目录。

    顺序:
        1. ``MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR`` 环境变量（覆盖）
        2. 默认 ``./skills``

    返回 Path 表示该目录或 None（表示禁用）。
    """
    raw = os.getenv("MODEM_LOG_ANALYZER_LOCAL_SKILLS_DIR", "./skills").strip()
    if not raw or raw == "none":
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (PROJECT_ROOT / raw).resolve()
    _assert_project_local(p)
    return p if p.exists() else None


def _github_source() -> str | None:
    """从 env 取 GitHub skill 仓库（"owner/repo@ref"）。"""
    return os.getenv("MODEM_LOG_ANALYZER_SKILLS_GITHUB") or None


def all_skill_sources() -> list[SkillSource]:
    """返回全部可用 skill 来源,供 SkillsMiddleware 装配。

    严格按硬规矩 8：只接受项目内路径与已声明的 GitHub 仓库。
    """
    out: list[SkillSource] = []

    local = _local_dir()
    if local is not None:
        out.append(SkillSource(label="local", kind="dir", location=str(local)))

    gh = _github_source()
    if gh:
        out.append(SkillSource(label="github", kind="github", location=gh))

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


if __name__ == "__main__":
    import json

    print(json.dumps([s.__dict__ for s in all_skill_sources()], indent=2))
