"""ModemLogAnalyzer —— CLI 输入校验与产物授权 (Unit 2)。

按 Plan Unit 2:
  - 集中所有"在调用 Agent/service 之前必须先做的事":
    * evb_log_path 必须存在、可读、非空、非目录。
    * output_dir 父目录必须存在, output_dir 本身不存在或将被覆盖。
    * control_log_path (可选) 存在则合法,缺失时合法。
    * 不修改磁盘;产物覆盖由调用方(service / Unit 6)按 overwrite 标志处理。
  - 抛出自定义 ``IntakeError`` (含 ``code`` 与人类可读 ``message``);
    **禁止**把 EVB 日志内容写入 message。
  - 接受 CLI 传的相对路径,并在 ``base_dir`` 下规范化为绝对路径。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ============================================================
# 错误类型
# ============================================================
class IntakeError(ValueError):
    """CLI 输入校验失败的统一错误类型。

    Args:
        code: 稳定的错误码(供测试 / i18n 使用)。
        message: 人类可读信息(不含日志原文)。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:  # pragma: no cover
        return self.message


# ============================================================
# 内部代理数据类
# ============================================================
@dataclass(frozen=True)
class RunRequestProxy:
    """CLI 与 intake 之间的最小可序列化数据载体。

    与 ``contracts.RunRequest`` 同构但保持解耦, 这样 intake 不需要依赖
    pydantic 模型, 单元测试可以脱离 pydantic 跑。
    """

    evb_log_path: str
    output_dir: str
    control_log_path: str | None
    label: str | None
    thread_id: str | None
    overwrite: bool
    base_dir: str | None = None


@dataclass(frozen=True)
class ValidatedRequest:
    """校验通过的请求。

    字段全部是规范化后的绝对路径(除非用户显式给出绝对路径)。
    """

    evb_log_path: str
    output_dir: str
    control_log_path: str | None
    label: str | None
    thread_id: str | None
    overwrite: bool


# ============================================================
# 路径解析与规范化
# ============================================================
def _resolve(path: str, base_dir: str | None) -> Path:
    """把 path 解析为绝对路径。

    - 如果是相对路径且提供了 base_dir, 在 base_dir 下解析。
    - 否则按 ``Path(path).resolve()`` 解析。
    """
    p = Path(path)
    if not p.is_absolute():
        if base_dir:
            p = Path(base_dir) / p
        else:
            p = p.resolve()
    else:
        p = p.resolve()
    return p


# ============================================================
# 主入口: validate_run_request
# ============================================================
def validate_run_request(req: RunRequestProxy) -> ValidatedRequest:
    """校验并规范化一次 analyze 请求。

    Raises:
        IntakeError: 任何非法输入。
    """
    base = req.base_dir or os.getcwd()

    # ---- 1. EVB 日志 ----
    evb = _resolve(req.evb_log_path, base)
    if not evb.exists():
        raise IntakeError("EVE_LOG_MISSING", f"evb-log not found: {evb}")
    if evb.is_dir():
        raise IntakeError("EVE_LOG_IS_DIR", f"evb-log is a directory, expected a file: {evb}")
    if not os.access(str(evb), os.R_OK):
        raise IntakeError("EVE_LOG_UNREADABLE", f"evb-log is not readable: {evb}")
    if evb.stat().st_size == 0:
        raise IntakeError("EVE_LOG_EMPTY", f"evb-log is empty: {evb}")

    # ---- 2. Output dir ----
    out = _resolve(req.output_dir, base)
    if out.exists() and not out.is_dir():
        raise IntakeError(
            "OUT_IS_FILE", f"output path is an existing file, expected a directory: {out}"
        )
    parent = out.parent  # 当 out 不存在时, parent 就是即将创建它的目录
    if not parent.exists():
        raise IntakeError("OUT_PARENT_MISSING", f"output parent directory does not exist: {parent}")
    if not os.access(str(parent), os.W_OK):
        raise IntakeError("OUT_PARENT_NOT_WRITABLE", f"output parent is not writable: {parent}")

    # ---- 3. 覆盖保护 ----
    if out.exists() and not req.overwrite:
        report = out / "report.md"
        json_p = out / "analysis.json"
        if report.exists():
            raise IntakeError(
                "OUT_REPORT_EXISTS",
                f"refusing to overwrite existing report.md in {out}; use --overwrite",
            )
        if json_p.exists():
            raise IntakeError(
                "OUT_JSON_EXISTS",
                f"refusing to overwrite existing analysis.json in {out}; use --overwrite",
            )

    # ---- 4. Control log (可选) ----
    ctrl: str | None = None
    if req.control_log_path:
        cpath = _resolve(req.control_log_path, base)
        if not cpath.exists():
            raise IntakeError("CONTROL_LOG_MISSING", f"control-log not found: {cpath}")
        if cpath.is_dir():
            raise IntakeError(
                "CONTROL_LOG_IS_DIR",
                f"control-log is a directory, expected a file: {cpath}",
            )
        if not os.access(str(cpath), os.R_OK):
            raise IntakeError("CONTROL_LOG_UNREADABLE", f"control-log is not readable: {cpath}")
        ctrl = str(cpath)

    # ---- 5. label 兜底 ----
    label = req.label or None
    if label is not None and len(label) > 200:
        raise IntakeError("LABEL_TOO_LONG", f"label exceeds 200 chars: {len(label)}")

    return ValidatedRequest(
        evb_log_path=str(evb),
        output_dir=str(out),
        control_log_path=ctrl,
        label=label,
        thread_id=req.thread_id,
        overwrite=req.overwrite,
    )


# ============================================================
# CLI 辅助: 把 CLI kwargs 转换为 RunRequestProxy
# ============================================================
def build_proxy_from_cli_kwargs(**kwargs: Any) -> RunRequestProxy:
    """把 click CLI 的 ``**kwargs`` 转换成 RunRequestProxy。

    兼容 CLI 调用: ``build_proxy_from_cli_kwargs(evb_log_path=..., output_dir=..., ...)``。
    """
    return RunRequestProxy(
        evb_log_path=kwargs["evb_log_path"],
        output_dir=kwargs["output_dir"],
        control_log_path=kwargs.get("control_log_path"),
        label=kwargs.get("label"),
        thread_id=kwargs.get("thread_id"),
        overwrite=kwargs.get("overwrite", False),
        base_dir=kwargs.get("base_dir"),
    )


__all__ = [
    "IntakeError",
    "RunRequestProxy",
    "ValidatedRequest",
    "validate_run_request",
    "build_proxy_from_cli_kwargs",
]
