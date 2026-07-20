"""SimpleTool —— 单元测试与无 langchain_core 环境下的工具替身。

真正的 langchain 工具在 ``build_tools()`` 路径下被 ``_as_simple_tool`` 适配;
测试可以读 ``.name`` 和 ``invoke({...})``,无需依赖 ``langchain_core.tools.BaseTool``。

设计动机:
  - Plan §1 R16 + S16 要求 Agent 不暴露危险工具;
  - 静态测试应能验证"工具名白名单"而无须拉起 deepagents / langchain。

若安装了 langchain_core, 在 ``tools.build_tools`` 中实际返回 langchain 的
``@tool`` 装饰对象;否则返回 SimpleTool。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class SimpleTool:
    """工具替身: 暴露 ``name`` 与 ``invoke({...})`` 接口。

    用法:
        >>> t = SimpleTool(name="read", fn=lambda *, path: path)
        >>> t.invoke({"path": "/tmp/x"})
    """

    name: str
    description: str = ""
    fn: Callable[..., Any] | None = None

    def invoke(self, args: dict[str, Any]) -> Any:
        if self.fn is None:
            raise RuntimeError(f"tool {self.name!r} has no fn bound")
        return self.fn(**args)


def _as_simple_tool(name: str, fn: Callable[..., Any], description: str = "") -> SimpleTool:
    """把一个普通函数包装成 SimpleTool。

    在 langchain 可用时,build_tools() 可以选择装饰为 ``@tool``;
    本层不依赖 langchain_core,因此静态测试可以独立校验。
    """
    return SimpleTool(name=name, description=description, fn=fn)


def try_langchain_tool(name: str, fn: Callable[..., Any], description: str = "") -> Any:
    """如果 langchain_core 可用,返回 langchain ``StructuredTool``;否则返回 SimpleTool。

    仅供 Agent 装配路径使用;静态测试不依赖此函数。
    """
    try:
        from langchain_core.tools import StructuredTool  # type: ignore
    except ImportError:
        return SimpleTool(name=name, description=description, fn=fn)

    # 用 StructuredTool.from_function 让 .invoke({"k": v}) 正确解包 kwargs。
    tool = StructuredTool.from_function(
        func=fn,
        name=name,
        description=description,
    )
    return tool


__all__ = ["SimpleTool", "_as_simple_tool", "try_langchain_tool"]
