# 作者：zcy
"""工具注册：应用启动时把可用工具注册进 ToolRegistry（参照 Dify 工具注册表思想）。

注册后，Agent/上层可按名称动态调用，不感知底层实现（可插拔）。
"""
from __future__ import annotations

from app.db.mock_listings import MOCK_LISTINGS
from app.tools.commute import get_commutator
from app.tools.registry import register_tool, get_registry

_COMMUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "from_address": {"type": "string", "description": "出发地（房源地址）"},
        "to_place": {"type": "string", "description": "通勤目的地"},
        "has_metro": {"type": "boolean", "description": "房源是否近地铁"},
    },
    "required": ["from_address", "to_place"],
}


@register_tool("commute_estimate", "估算两点通勤分钟数（可插拔：近似/地图）", _COMMUTE_SCHEMA)
def commute_estimate(from_address: str, to_place: str, has_metro: bool = False) -> float:
    return get_commutator().estimate_minutes(from_address, to_place, has_metro)


_AVG_SCHEMA = {
    "type": "object",
    "properties": {"district": {"type": "string", "description": "区域名称"}},
    "required": ["district"],
}


@register_tool("district_avg_price", "查询某区域房源均价（行情）", _AVG_SCHEMA)
def district_avg_price(district: str) -> float | None:
    prices = [r["price"] for r in MOCK_LISTINGS if r["district"] == district and r["price"]]
    return round(sum(prices) / len(prices), 2) if prices else None


def register_builtin_tools() -> None:
    """显式触发注册（确保模块被 import 时工具已就绪）。"""
    _ = get_registry().names()
