"""ModemLogAnalyzer —— Run Context (U1)。

按 Plan §5 Unit 1 + S4:
  - ``set / get / clear`` 在进程内保存**本次 run** 的预处理 bundle。
  - **真并发隔离**: 用 ``contextvars.ContextVar`` 而不是 module-level dict + Lock。
    Gateway FastAPI / 多个 worker 并发时, 每次 invoke 拿到的是本次 run 的 bundle;
    与 LangGraph checkpointer 的 thread_id 配合, 即便两条 /runs 并发也不会读到对方证据。
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

历史 (本次重写):
  - 旧实现使用 ``module-level dict + threading.Lock`` —— 看似加锁, 实际**没有**
    并发隔离: 两条并发 run 在两次 set/get 之间会相互覆盖。Plan U1 要求"线程/run 隔离",
    现改为 ``ContextVar`` 真正满足该契约。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


_BUNDLE: ContextVar[dict[str, Any] | None] = ContextVar("modem_la_bundle", default=None)


def set(bundle: dict[str, Any]) -> object:
    """写入本次 run 的 bundle。

    返回 ``Token`` 供 ``reset(token)`` 还原, 供 runner 在 finally 中精确清除
    本次写入而不影响其他 task token。线程 / asyncio task 之间天然隔离。
    """
    return _BUNDLE.set(dict(bundle))  # 浅拷贝, 防止外部 mutate


def get() -> dict[str, Any] | None:
    """读取本次 run 的 bundle; 没有 set → 返回 None。"""
    val = _BUNDLE.get()
    if val is None:
        return None
    return dict(val)


def clear() -> None:
    """清空当前 task 的 bundle。

    注意: ``ContextVar.set`` 返回 Token, 严格语义是用 ``_BUNDLE.reset(token)``。
    本接口保留 module-level API, 直接 reset 当前值。
    """
    _BUNDLE.set(None)


def reset(token: object) -> None:
    """按 set() 返回的 token 精确还原; 供 runner 在 finally 调用以避免影响
    嵌套调用者 (例如测试 fixture 嵌套)."""
    _BUNDLE.reset(token)  # type: ignore[arg-type]


def require() -> dict[str, Any]:
    """必须 set 才能调用; 否则抛出 RuntimeError (供工具内部捕获→统一错误格式)。"""
    bundle = get()
    if bundle is None:
        raise RuntimeError(
            "run_context is empty; agent tools must be called only after runner.preprocess()"
        )
    return bundle


__all__ = ["set", "get", "clear", "reset", "require"]