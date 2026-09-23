# 作者：zcy
"""工具注册表（参照 Dify core/tools 的注册表思想，代码自研）。

统一注册 Agent 可用工具（房源源、通勤测算、行情），用 Pydantic 生成
工具 Schema，上层 Agent 按名称调用，不感知底层实现（可插拔）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.models.schemas import RentRequirement


@dataclass
class Tool:
    """一个可被 Agent 调用的工具。"""
    name: str
    description: str
    params_schema: dict[str, Any]          # JSON Schema（Pydantic 生成）
    callable: Callable[..., Any]


class ToolRegistry:
    """工具注册表：注册 + 按名调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"工具不存在: {name}")
        return tool.callable(**kwargs)


_registry = ToolRegistry()


def register_tool(
    name: str, description: str, params_schema: dict[str, Any]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：把一个函数注册为工具。"""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _registry.register(Tool(name=name, description=description, params_schema=params_schema, callable=fn))
        return fn

    return deco


def get_registry() -> ToolRegistry:
    return _registry
