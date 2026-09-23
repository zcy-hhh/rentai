# 作者：zcy
"""M2 测试：避坑检查（引用约束）、看房清单生成（HITL 前置）。"""
from __future__ import annotations

from app.agents.graph import rent_graph
from app.db.mock_listings import MOCK_LISTINGS
from app.models.schemas import Listing, RentRequirement
from app.rag.knowledge_base import check_listing


def _req(**kw) -> RentRequirement:
    d = dict(max_price=6000, room_types=["1室", "2室", "3室"])
    d.update(kw)
    return RentRequirement(**d)


def test_viewing_list_generated() -> None:
    r = rent_graph.invoke({"requirement": _req(district="滨湖", max_price=4000)})
    vl = r["viewing_list"]
    assert vl.status == "pending"
    assert vl.candidates


def test_viewing_list_has_verify_and_ask_items() -> None:
    r = rent_graph.invoke({"requirement": _req(district="滨湖", max_price=4000)})
    vl = r["viewing_list"]
    assert vl.verify_items or vl.ask_items


def test_risk_notes_have_reference() -> None:
    """引用约束：每条风险必须带依据来源（防幻觉）。"""
    r = rent_graph.invoke({"requirement": _req(district="新吴", max_price=6000)})
    vl = r["viewing_list"]
    assert vl.candidates
    for c in vl.candidates:
        for risk in c.risks:
            assert risk.reference


def test_group_rent_risk_detected() -> None:
    """疑似群租房源应被识别。"""
    listing = Listing(**MOCK_LISTINGS[14])  # mock-015 含"疑似群租"
    kinds = {x.kind for x in check_listing(listing)}
    assert "疑似群租" in kinds


def test_risk_with_avg_price_ratio() -> None:
    """低于区域均价且未验证的房源触发「疑似虚假房源」。"""
    r = rent_graph.invoke({"requirement": _req(district="新吴", max_price=6000)})
    vl = r["viewing_list"]
    kinds = {risk.kind for c in vl.candidates for risk in c.risks}
    assert "疑似虚假房源" in kinds  # mock-015 价格 1500 < 新吴均价*0.7 且未验证
