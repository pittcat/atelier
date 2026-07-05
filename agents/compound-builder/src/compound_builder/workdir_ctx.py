"""CompoundBuilder —— 当前 run 的 workdir 上下文。

节点在调用 tools / worker 前 ``set_workdir(state["workdir"])``,
工具函数通过 ``resolve_path`` / ``get_workdir`` 定位文件与 subprocess cwd。
"""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

_workdir: ContextVar[Path] = ContextVar("compound_builder_workdir", default=Path("."))


def set_workdir(path: str | Path) -> Path:
    p = Path(path).resolve()
    _workdir.set(p)
    return p


def get_workdir() -> Path:
    return _workdir.get()


def resolve_path(rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return get_workdir() / p


__all__ = ["set_workdir", "get_workdir", "resolve_path"]
