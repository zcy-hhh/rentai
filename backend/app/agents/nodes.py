# 作者：zcy
"""LangGraph 编排节点：检索 → 硬条件过滤 → 评分排序 → 避坑检查 → 看房清单。

M1 用确定性规则保证链路可验证；M2 加入避坑检查（引用约束）与看房清单（HITL）；
M3 加入通勤测算（可插拔 commutator）。
"""
from __future__ import annotations

import uuid

from app.db.mock_listings import MOCK_LISTINGS
from app.models.schemas import CandidateListing, Listing, RentRequirement, ViewingList
from app.rag.retriever import retrieve_risks
from app.tools.commute import get_commutator
from app.tools.listing_source import get_sources


# ---------- 检索 ----------

def node_retrieve(state: dict) -> dict:
    """从所有数据源聚合候选房源（粗筛，不做细筛）。"""
    req: RentRequirement = state["requirement"]
    raw: list[Listing] = []
    for src in get_sources():
        raw.extend(src.search(req))
    return {"raw": raw}


# ---------- 硬条件过滤 ----------

def node_filter(state: dict) -> dict:
    """硬条件过滤：价格上限、最小面积、可接受户型、偏好标签（近地铁/精装等）。"""
    req: RentRequirement = state["requirement"]
    filtered: list[Listing] = []
    for listing in state["raw"]:
        if listing.price > req.max_price:
            continue
        if req.min_area is not None and listing.area < req.min_area:
            continue
        if req.room_types and not any(rt in listing.room_type for rt in req.room_types):
            continue
        # 偏好标签过滤：用户指定的标签必须全部命中（如 近地铁、精装、电梯）
        if req.tags and not all(t in listing.facilities for t in req.tags):
            continue
        filtered.append(listing)
    return {"filtered": filtered}


# ---------- 评分排序（含通勤测算） ----------

def node_rank(state: dict) -> dict:
    """按需求匹配度评分并排序（确定性规则 + 通勤测算，可复现、可评测）。"""
    req: RentRequirement = state["requirement"]
    ranked: list[CandidateListing] = []
    commutator = get_commutator()
    for listing in state["filtered"]:
        commute = None
        if req.commute_to:
            commute = commutator.estimate_minutes(
                listing.address or listing.district, req.commute_to, "近地铁" in listing.facilities
            )
        score, reasons = _score(req, listing, commute)
        ranked.append(
            CandidateListing(**listing.model_dump(), match_score=score, match_reasons=reasons, commute_minutes=commute)
        )
    ranked.sort(key=lambda c: c.match_score, reverse=True)
    return {"ranked": ranked}


def _score(req: RentRequirement, listing: Listing, commute: float | None = None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    # 价格：越低于预算分越高
    if listing.price <= req.max_price * 0.8:
        score += 30
        reasons.append("价格低于预算，性价比高")
    else:
        score += 20
        reasons.append("价格在预算内")

    # 面积
    if req.min_area and listing.area >= req.min_area * 1.3:
        score += 10
        reasons.append("面积充足")

    # 户型
    if listing.room_type in req.room_types:
        score += 10

    # 平台验证
    if listing.is_verified:
        score += 10
        reasons.append("平台已验证")

    # 风险扣分
    if listing.risk_flags:
        score -= 15 * len(listing.risk_flags)
        reasons.append(f"风险提示：{'、'.join(listing.risk_flags[:2])}")

    # 关键设施加分
    for f in ("近地铁", "精装", "电梯"):
        if f in listing.facilities:
            score += 5

    # 通勤测算（M3：确定性估算，可替换地图 API）
    if req.commute_to and commute is not None:
        if req.commute_max_minutes is not None:
            if commute <= req.commute_max_minutes:
                score += 10
                reasons.append(f"通勤约 {commute} 分钟，在可接受范围")
            else:
                score -= 10
                reasons.append(f"通勤约 {commute} 分钟，超出上限")
        else:
            score += 5
            reasons.append(f"通勤约 {commute} 分钟")

    return round(score, 1), reasons


# ---------- 避坑检查（RAG 检索 + 引用约束） ----------

def _district_avg_price(district: str) -> float | None:
    """计算某区域房源均价（M2 用模拟数据估算；M4 换真实行情）。"""
    prices = [r["price"] for r in MOCK_LISTINGS if r["district"] == district and r["price"]]
    return round(sum(prices) / len(prices), 2) if prices else None


def node_risk_check(state: dict) -> dict:
    """对每个候选执行避坑检查，附加带引用的风险标注。"""
    ranked: list[CandidateListing] = state["ranked"]
    for c in ranked:
        c.risks = retrieve_risks(c, district_avg_price=_district_avg_price(c.district))
    return {"ranked": ranked}


# ---------- 看房清单（HITL 前置产物） ----------

def node_build_list(state: dict) -> dict:
    """组装看房清单：候选 + 现场核实项 + 问询清单，进入 HITL 待确认状态。"""
    req: RentRequirement = state["requirement"]
    ranked: list[CandidateListing] = state["ranked"]
    verify_items, ask_items = _build_items(ranked)
    viewing_list = ViewingList(
        list_id=uuid.uuid4().hex[:12],
        requirement=req,
        candidates=ranked,
        verify_items=verify_items,
        ask_items=ask_items,
        status="pending",
    )
    return {"viewing_list": viewing_list}


def _build_items(ranked: list[CandidateListing]) -> tuple[list[str], list[str]]:
    """根据候选与风险生成"现场核实项"和"问询清单"。"""
    verify: set[str] = set()
    ask: set[str] = set()
    for c in ranked:
        for r in c.risks:
            if r.kind in ("疑似群租", "疑似虚假房源"):
                verify.add(f"{c.title}：现场核实「{r.kind}」，确认真实性/合规性")
            elif r.kind in ("商水商电", "中介费提示", "合同陷阱提示"):
                ask.add(f"{c.title}：问清「{r.kind}」的具体标准与条款")
        ask.add(f"{c.title}：确认押金退还、维修责任与违约条款")
        if "近地铁" not in c.facilities:
            verify.add(f"{c.title}：实测到最近地铁/通勤时间")
    return sorted(verify)[:8], sorted(ask)[:8]
