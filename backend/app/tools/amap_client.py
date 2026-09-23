# 作者：zcy
"""高德开放平台（Web 服务）客户端：真实 POI / 地理编码 / 公交通勤（M11 高德 MCP 数据层）。

所有函数失败都返回 None / [] 并静默降级（不因外部 API 抖动挂死 Agent）：
- 无 AMAP_KEY → 全部返回 None（未配置时不打扰主流程）
- 网络/接口异常 → 返回 None，Agent 可继续走原有逻辑
"""
from __future__ import annotations

from typing import Any

import requests

from app.core.config import settings

_BASE = "https://restapi.amap.com/v3"


def _amap_get(path: str, params: dict, timeout: int = 6) -> dict | None:
    """请求高德 Web 服务；status=1 才返回，否则 None。"""
    if not settings.amap_key:
        return None
    params = dict(params)
    params["key"] = settings.amap_key
    try:
        r = requests.get(_BASE + path, params=params, timeout=timeout)
        data = r.json()
        return data if data.get("status") == "1" else None
    except Exception:
        return None


def amap_geocode(address: str) -> dict | None:
    """地理编码：地址 → 经纬度。返回 {lng, lat, formatted} 或 None。"""
    if not address:
        return None
    data = _amap_get("/geocode/geo", {"address": address, "city": "无锡"})
    if not data or not data.get("geocodes"):
        return None
    gc = data["geocodes"][0]
    loc = gc.get("location") or ""
    if "," not in loc:
        return None
    lng, lat = loc.split(",", 1)
    return {
        "lng": float(lng),
        "lat": float(lat),
        "formatted": gc.get("formatted_address") or "",
    }


def amap_regeo(lng: float, lat: float) -> dict | None:
    """逆地理编码：经纬度 → 行政区/街道。返回 {district, township, formatted} 或 None。"""
    try:
        data = _amap_get("/geocode/regeo", {"location": f"{lng},{lat}"})
    except Exception:
        return None
    if not data or "regeocode" not in data:
        return None
    rc = data["regeocode"]
    ac = rc.get("addressComponent", {}) or {}
    return {
        "district": ac.get("district") or "",
        "township": ac.get("township") or "",
        "formatted": rc.get("formatted_address") or "",
    }


def amap_poi_around(
    lng: float, lat: float, radius: int = 2000, keywords: str = ""
) -> list[dict]:
    """周边 POI 检索（地铁/超市/学校/医院/商圈等）。返回 [{name,type,distance,address}, ...] 或 []。"""
    params: dict[str, Any] = {"location": f"{lng},{lat}", "radius": radius, "offset": 10}
    if keywords:
        params["keywords"] = keywords
    data = _amap_get("/place/around", params)
    if not data or "pois" not in data:
        return []
    pois: list[dict] = []
    for p in (data.get("pois") or [])[:10]:
        loc = p.get("location") or ""
        pois.append({
            "name": p.get("name") or "",
            "type": p.get("type") or "",
            "distance": p.get("distance") or "",
            "address": p.get("address") or "",
        })
    return pois


def amap_transit(
    origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float
) -> dict | None:
    """公交通勤（跨城整合方案）：返回 {minutes, distance} 或 None。"""
    data = _amap_get(
        "/direction/transit/integrated",
        {
            "origin": f"{origin_lng},{origin_lat}",
            "destination": f"{dest_lng},{dest_lat}",
        },
    )
    if not data or "route" not in data:
        return None
    transits = data["route"].get("transits") or []
    if not transits:
        return None
    t = transits[0]
    try:
        minutes = int(int(t.get("duration", 0)) / 60)
    except (ValueError, TypeError):
        minutes = 0
    return {"minutes": minutes, "distance": t.get("distance") or ""}
