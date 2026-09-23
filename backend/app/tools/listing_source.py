# 作者：zcy
"""房源数据源抽象层。

M1 使用模拟源跑通链路；M3 通过 MCP 适配器接入真实平台（贝壳/58/自如…）。
所有数据源实现 `ListingSource` 协议，返回统一结构，上层（Agent）不感知来源差异。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.db.beike_real import BEIKE_REAL
from app.db.mock_listings import MOCK_LISTINGS
from app.db.synthetic import generate_synthetic
from app.models.schemas import Listing, RentRequirement


@lru_cache(maxsize=1)
def _synthetic_raw() -> list[dict]:
    """合成房源原始数据（固定种子，可复现；缓存避免每次检索重复生成）。"""
    return generate_synthetic(200)


def _norm_district(s: str) -> str:
    """区域输入规范化：去除「区」后缀与空格，实现『滨湖区/滨湖』、『新吴区/新吴』互通。"""
    return s.replace("区", "").strip()


@runtime_checkable
class ListingSource(Protocol):
    """房源数据源协议。任何数据源必须实现 search。"""
    name: str

    def search(self, requirement: RentRequirement) -> list[Listing]:
        """按需求检索，返回原始候选（粗筛，细筛交给 Agent 的 filter 节点）。"""


class MockListingSource:
    """模拟数据源：从内置数据按区域粗筛，返回全部候选。"""

    name = "mock"

    def search(self, requirement: RentRequirement) -> list[Listing]:
        raw = MOCK_LISTINGS
        if requirement.district:
            dn = _norm_district(requirement.district)
            raw = [r for r in raw if dn in _norm_district(r["district"])]
        return [Listing(**r) for r in raw]


class SyntheticListingSource:
    """合成数据源（方案 C 扩量）：200 套中文风格房源，实现同一 ListingSource 协议。

    与 mock 源并列启用，让检索主链路覆盖 218 套，演示"数据源可插拔"。
    """

    name = "synthetic"

    def search(self, requirement: RentRequirement) -> list[Listing]:
        raw = _synthetic_raw()
        if requirement.district:
            dn = _norm_district(requirement.district)
            raw = [r for r in raw if dn in _norm_district(r["district"])]
        return [Listing(**r) for r in raw]


class BeikeListingSource:
    """真实数据源（贝壳找房·无锡租房）：真实房源 + 真实链接。

    M3 里程碑：从贝壳首页抓取的真实房源（含真实 href），替换早期模拟源，让
    大模型推荐的房源带可点击的真实链接。字段与 mock/合成源一致（统一 Listing 协议）。
    """

    name = "beike"

    def search(self, requirement: RentRequirement) -> list[Listing]:
        raw = BEIKE_REAL
        if requirement.district:
            dn = _norm_district(requirement.district)
            raw = [r for r in raw if dn in _norm_district(r["district"])]
        return [Listing(**r) for r in raw]


def get_sources() -> list[object]:
    """返回当前启用的数据源列表（真实源优先；mock/合成扩量兜底）。"""
    return [BeikeListingSource(), MockListingSource(), SyntheticListingSource()]
