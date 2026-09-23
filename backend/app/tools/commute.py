# 作者：zcy
"""通勤测算抽象：可插拔实现（距离近似 / 地图 API）。

M3 用"直线距离近似 + 地铁权重"的确定性估算（不依赖 key、可测试）；
提供地图 API 实现骨架，配置 key 后自动切换。
"""
from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

from app.core.config import settings


@runtime_checkable
class Commutator(Protocol):
    """通勤测算协议。"""
    name: str

    def estimate_minutes(self, from_address: str, to_place: str, has_metro: bool) -> float: ...


class DistanceApproxCommutator:
    """确定性近似：按城市坐标/关键字估算，可复现、可测试。"""
    name = "approx"

    # 简单城市网格：区 -> (x, y)（演示数据）
    _POINTS = {
        "河西": (3, 5), "滨湖": (6, 3), "梁溪": (5, 5), "锡山": (8, 4),
        "新吴": (7, 2), "惠山": (3, 2), "高新区": (6, 2),
    }

    def estimate_minutes(self, from_address: str, to_place: str, has_metro: bool) -> float:
        # 从地址中识别区域关键字
        import re

        def locate(s: str):
            for k, v in self._POINTS.items():
                if k in s:
                    return v
            return (5, 5)

        p1, p2 = locate(from_address), locate(to_place)
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        minutes = dist * 12          # 每格约 12 分钟
        if has_metro:
            minutes *= 0.7           # 近地铁打折
        return round(minutes, 1)


# 地图 API 实现骨架（配置 key 后启用）
# class MapApiCommutator(Commutator):
#     name = "map"
#     def estimate_minutes(self, from_address, to_place, has_metro):
#         # 调用高德/百度 web 服务：/direction 计算通勤时长
#         ...


def get_commutator() -> Commutator:
    """返回当前启用的通勤实现（M3 前为确定性近似）。"""
    return DistanceApproxCommutator()
