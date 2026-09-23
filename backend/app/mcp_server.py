# 作者：zcy
"""RentAI MCP Server：把房源检索能力暴露为标准 MCP 工具。

任何支持 MCP 的客户端（Claude Desktop、其他 Agent 等）可通过本 server
连接并调用 `search_rent_listings` 检索无锡真实房源（贝壳，含真实链接）与
合成房源。项目内 Agent（react_tools.search_listings）也经 MCP client 连接调用，
体现"Agent 通过 MCP 协议使用工具"的架构。

运行方式（stdio，MCP 客户端默认接入方式）：
    uv run python -m app.mcp_server
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.models.schemas import RentRequirement
from app.tools.listing_source import get_sources
from app.tools import amap_client as amap

# MCP Server 实例（server name 供客户端识别）
mcp = FastMCP("rentai-rental")


def _listing_to_dict(l: Any) -> dict:
    return {
        "id": l.id,
        "title": l.title,
        "source": l.source,
        "url": l.url,
        "district": l.district,
        "address": l.address,
        "price": l.price,
        "area": l.area,
        "room_type": l.room_type,
        "orientation": l.orientation,
        "floor": l.floor,
        "facilities": l.facilities,
        "is_verified": l.is_verified,
        "description": l.description,
    }


@mcp.tool()
def search_rent_listings(
    district: str = "",
    max_price: float = 0,
    min_area: float = 0,
    room_type: str = "",
) -> list[dict]:
    """检索无锡租房房源（真实贝壳 + 合成演示数据）。

    Args:
        district: 意向区域，如 "滨湖"、"梁溪"、"新吴"、"锡山"、"惠山"（不带"区"也可）。
        max_price: 月租金上限（元），0 表示不限。
        min_area: 最小面积（㎡），0 表示不限。
        room_type: 户型，如 "1室"、"2室"、"3室"，空表示不限。

    Returns:
        房源列表。source="beike" 的为真实房源且 url 为可点击的贝壳详情链接；
        source="synthetic"/"mock" 的为演示数据，url 为占位。
    """
    req = RentRequirement(
        district=district or None,
        max_price=max_price if max_price > 0 else 999999,
        min_area=min_area or None,
        room_types=[room_type] if room_type else ["1室", "2室", "3室"],
    )
    results: list[dict] = []
    seen: set[str] = set()
    for src in get_sources():
        for listing in src.search(req):
            if listing.id in seen:
                continue
            seen.add(listing.id)
            d = _listing_to_dict(listing)
            if req.max_price < 999999 and listing.price > req.max_price:
                continue
            if req.min_area and listing.area < req.min_area:
                continue
            if req.room_types and listing.room_type not in req.room_types:
                continue
            results.append(d)
    # 真实源优先排序，便于推荐命中带链接房源
    results.sort(key=lambda x: 0 if x["source"] == "beike" else 1)
    return results


@mcp.tool()
def get_listing_detail(listing_id: str) -> dict | None:
    """按房源 id 获取详情（含真实链接 url）。

    Args:
        listing_id: 房源 id，如 "beike-WX2212415198885576704"。
    """
    for src in get_sources():
        for listing in src.search(RentRequirement(max_price=999999)):
            if listing.id == listing_id:
                return _listing_to_dict(listing)
    return None


@mcp.tool()
def amap_geocode(address: str) -> dict | None:
    """高德地理编码：把地址/小区名解析成真实经纬度。"""
    return amap.amap_geocode(address)


@mcp.tool()
def amap_poi_around(lng: float, lat: float, radius: int = 2000, keywords: str = "") -> list[dict]:
    """高德周边 POI 检索（地铁/超市/学校/医院等），返回名称/类型/距离。"""
    return amap.amap_poi_around(lng, lat, radius=radius, keywords=keywords)


@mcp.tool()
def amap_commute(origin: str, destination: str) -> dict | None:
    """高德公交通勤时长估算（分钟/距离），输入起终点地址。"""
    o = amap.amap_geocode(origin)
    d = amap.amap_geocode(destination)
    if not o or not d:
        return None
    t = amap.amap_transit(o["lng"], o["lat"], d["lng"], d["lat"])
    if not t:
        return None
    return {"from": origin, "to": destination, "minutes": t["minutes"], "distance": t["distance"]}


if __name__ == "__main__":
    mcp.run(transport="stdio")
