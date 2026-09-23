# 作者：zcy
"""ReAct Agent 工具集：把五个环节暴露成"模型可自主调用的工具"（M9）。

设计要点（面试必答）：
- 数据不通过工具参数/返回值传递（几百条 listing 会烧 token），而是放在共享
  AgentCtx 里，工具只操作 ctx 并返回**摘要**给模型观察。
- 模型只负责"决策"：何时调 search/filter/rank/risk/build，自主决定顺序与步数；
  执行由确定性函数完成（可复现、可评测）——这是"模型推理 + 工具执行"的 Agent 范式。
"""
from __future__ import annotations

import uuid

from langchain_core.tools import tool

from app.agents.nodes import _build_items, _district_avg_price, _score
from app.models.schemas import CandidateListing, Listing, RentRequirement, ViewingList
from app.rag.hybrid_retriever import hybrid_search
from app.rag.retriever import retrieve_risks
from app.tools.commute import get_commutator
from app.tools import amap_client as amap


class AgentCtx:
    """Agent 执行上下文：一次运行共享一份，避免 listing 全量进出工具参数。"""

    req: RentRequirement | None = None
    raw: list[Listing] = []
    filtered: list[Listing] = []
    ranked: list[CandidateListing] = []
    viewing_list: ViewingList | None = None


_ctx = AgentCtx()


def reset_ctx(req: RentRequirement) -> None:
    _ctx.req = req
    _ctx.raw = []
    _ctx.filtered = []
    _ctx.ranked = []
    _ctx.viewing_list = None


def _summary(title: str, items: list, limit: int = 10) -> str:
    """工具返回给模型的摘要（前 N 条，控 token）。"""
    lines = [
        f"- {it.title} ￥{int(it.price)} {int(it.area)}㎡ 匹配{getattr(it, 'match_score', '-')}分"
        for it in items[:limit]
    ]
    head = "\n".join(lines)
    return f"{title}：共 {len(items)} 套。\n{head}"


@tool
async def search_listings() -> str:
    """检索房源：按用户需求混合检索（关键词+语义+重排）召回候选房源。必须先调用。"""
    assert _ctx.req is not None
    _ctx.raw = await hybrid_search(_ctx.req)
    return _summary("检索到候选房源", _ctx.raw)


@tool
def filter_hard() -> str:
    """硬条件过滤：从已检索候选里筛掉不符合价格上限/最小面积/户型的房源。"""
    req = _ctx.req
    assert req is not None
    kept = []
    for l in _ctx.raw:
        if l.price > req.max_price:
            continue
        if req.min_area is not None and l.area < req.min_area:
            continue
        if req.room_types and not any(rt in l.room_type for rt in req.room_types):
            continue
        kept.append(l)
    _ctx.filtered = kept
    return _summary("硬条件过滤后（满足价格/面积/户型）", kept)


@tool
def score_rank(sort_by: str = "score") -> str:
    """评分排序：对过滤后的房源按匹配度打分。sort_by 可选 'score'(匹配度降序) / 'price_asc'(价格升序，最便宜在前) / 'price_desc'(价格降序) / 'area_desc'(面积降序)。"""
    req = _ctx.req
    assert req is not None
    commutator = get_commutator()
    ranked = []
    for l in _ctx.filtered:
        commute = None
        if req.commute_to:
            commute = commutator.estimate_minutes(
                l.address or l.district, req.commute_to, "近地铁" in l.facilities
            )
        score, reasons = _score(req, l, commute)
        ranked.append(
            CandidateListing(**l.model_dump(), match_score=score, match_reasons=reasons, commute_minutes=commute)
        )
    if sort_by == "price_asc":
        ranked.sort(key=lambda c: c.price)
        label = "价格升序（最便宜在前）"
    elif sort_by == "price_desc":
        ranked.sort(key=lambda c: -c.price)
        label = "价格降序"
    elif sort_by == "area_desc":
        ranked.sort(key=lambda c: -c.area)
        label = "面积降序"
    else:
        ranked.sort(key=lambda c: c.match_score, reverse=True)
        label = "匹配度降序"
    _ctx.ranked = ranked
    return _summary(f"评分排序后（{label}）", ranked)


@tool
def check_risks() -> str:
    """避坑检查：对评分后的候选房源标注风险（带引用依据）。"""
    for c in _ctx.ranked:
        c.risks = retrieve_risks(c, district_avg_price=_district_avg_price(c.district))
    flagged = sum(1 for c in _ctx.ranked if c.risks)
    return f"避坑检查完成：{flagged} 套候选有风险标注，其余无风险。"


@tool
def build_viewing_list(top_k: int = 0) -> str:
    """生成看房清单：基于当前候选生成最终清单。若尚未排序则直接使用过滤结果（无需 score_rank 也能生成）。top_k>0 时只取前 top_k 套，否则包含全部。"""
    req = _ctx.req
    assert req is not None
    ranked = _ctx.ranked
    if not ranked:
        ranked = [
            CandidateListing(**l.model_dump(), match_score=0.0, match_reasons=[], commute_minutes=None)
            for l in (_ctx.filtered or [])
        ]
    if top_k and top_k > 0:
        ranked = ranked[:top_k]
    verify_items, ask_items = _build_items(ranked)
    _ctx.viewing_list = ViewingList(
        list_id=uuid.uuid4().hex[:12],
        requirement=req,
        candidates=ranked,
        verify_items=verify_items,
        ask_items=ask_items,
        status="pending",
    )
    return f"看房清单已生成：{_ctx.viewing_list.list_id}，含 {len(ranked)} 套房源（top_k={top_k}）。"


@tool
def amap_geocode(address: str) -> str:
    """地理编码：把地址/小区名解析成真实经纬度。需要精确位置、或后续要用周边/通勤工具时，先调用本工具获取坐标。"""
    g = amap.amap_geocode(address)
    if not g:
        return f"高德未能定位「{address}」（可能未配置 AMAP_KEY 或地址不可识别），可继续使用原地址。"
    return f"「{address}」定位到：{g['formatted']}，经纬度 {g['lng']},{g['lat']}。"


@tool
def amap_poi_around(address: str, radius: int = 2000, keywords: str = "") -> str:
    """周边配套检索：输入房源地址（或经纬度），返回周边地铁/超市/学校/医院等 POI 及距离。
    keywords 可选（如"地铁站"、"超市"、"医院"、"学校"），为空时返回综合 POI。"""
    g = amap.amap_geocode(address)
    if not g:
        return f"无法定位「{address}」，无法检索周边。"
    pois = amap.amap_poi_around(g["lng"], g["lat"], radius=radius, keywords=keywords)
    if not pois:
        return f"「{address}」周边 {radius} 米内未检索到{'「'+keywords+'」' if keywords else '相关'} POI。"
    lines = "\n".join(f"- {p['name']}（{p['type']}）约{p['distance']}米" for p in pois[:8])
    return f"「{address}」周边 {radius} 米内（{'关键词:'+keywords if keywords else '综合'}）：\n{lines}"


@tool
def amap_commute(from_address: str, to_address: str) -> str:
    """公交通勤估算：计算从房源/地点到通勤目的地的公共交通时长（分钟）与距离，使用高德真实数据。"""
    o = amap.amap_geocode(from_address)
    d = amap.amap_geocode(to_address)
    if not o or not d:
        return f"无法定位起终点（{from_address} / {to_address}），无法估算通勤。"
    t = amap.amap_transit(o["lng"], o["lat"], d["lng"], d["lat"])
    if not t:
        return f"高德未返回从「{from_address}」到「{to_address}」的公交通勤方案。"
    return f"从「{from_address}」到「{to_address}」公交通勤约 {t['minutes']} 分钟，约 {t['distance']} 米。"


tools = [
    search_listings,
    filter_hard,
    score_rank,
    check_risks,
    build_viewing_list,
    amap_geocode,
    amap_poi_around,
    amap_commute,
]
