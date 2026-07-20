"""ModemLogAnalyzer —— Run Context (U1)。

按 Plan §5 Unit 1 + S4:
  - ``set / get / clear`` 在进程内保存**本次 run** 的预处理 bundle。
  - 线程/run 隔离: 每个线程独立; 不暴露给 agent 自身之外的全局。
  - Bundle 必须为 JSON 序列化友好 (dict[str, Any], list 元素纯 Python 类型)。
  - bundle schema (最小):
        {
          "run_label": str,
          "evb_log_path": str | None,
          "command_summary": [{"ref_id": str, "command": str}, ...],
          "evidence_refs": [str, ...],          # 含 EV-NNNN
          "control_summary": list[dict] | None,  # 可选: 控制脚本要点
          "interrupt_request": dict | None,
        }
  - 不允许 Agent 调工具直接修改 bundle (set / clear 只由 runner 调用)。

设计动机:
  - ``build_tools()`` 在 deepagents 装配时静态返回;无法把所有 run 上下文硬编码到 tool。
  - 让 tools 通过 ``run_context`` 间接读, 既保留 ``langchain_core`` 装饰形态,
    又不阻塞生产环境运行多个并发 run。
"""

from __future__ import annotations

import threading
from typing import Any


_BUNDLE: dict[str, Any] | None = None
_LOCK = threading.Lock()


def set(bundle: dict[str, Any]) -> None:
    """写入本次 run 的 bundle。覆盖旧的 (同一 runner 串行复用)。"""
    global _BUNDLE
    with _LOCK:
        _BUNDLE = dict(bundle)  # 浅拷贝, 防止外部 mutate


def get() -> dict[str, Any] | None:
    """读取本次 run 的 bundle; 没有 set → 返回 None。"""
    with _LOCK:
        if _BUNDLE is None:
            return None
        return dict(_BUNDLE)


def clear() -> None:
    """清空 bundle。runner 终止时必须调用, 避免下一 run 读到上一 run 的证据。"""
    global _BUNDLE
    with _LOCK:
        _BUNDLE = None


def require() -> dict[str, Any]:
    """必须 set 才能调用; 否则抛出 RuntimeError (供工具内部捕获→统一错误格式)。"""
    bundle = get()
    if bundle is None:
        raise RuntimeError(
            "run_context is empty; agent tools must be called only after runner.preprocess()"
        )
    return bundle


__all__ = ["set", "get", "clear", "require"]