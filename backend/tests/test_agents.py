# 作者：zcy
"""M1 Agent 编排单元测试：验证检索→过滤→排序链路与硬条件约束。"""
from __future__ import annotations

from app.agents.graph import rent_graph
from app.models.schemas import RentRequirement


def test_candidates_satisfy_hard_conditions() -> None:
    """所有返回候选必须满足价格/户型硬条件。"""
    req = RentRequirement(max_price=4000, district="滨湖", room_types=["1室", "2室"])
    result = rent_graph.invoke({"requirement": req})
    for c in result["ranked"]:
        assert c.price <= req.max_price
        assert c.room_type in req.room_types


def test_budget_filter_works() -> None:
    """低于预算上限的房源应被过滤。"""
    req = RentRequirement(max_price=2000, district="滨湖")
    result = rent_graph.invoke({"requirement": req})
    assert result["ranked"]
    for c in result["ranked"]:
        assert c.price <= 2000


def test_ranked_desc_by_score() -> None:
    """候选应按匹配分数降序排列。"""
    req = RentRequirement(max_price=6000, district="滨湖", room_types=["1室"])
    result = rent_graph.invoke({"requirement": req})
    scores = [c.match_score for c in result["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_candidate_has_match_reasons() -> None:
    """每个候选必须带评分理由（可解释性）。"""
    req = RentRequirement(max_price=4000, district="滨湖", room_types=["1室"])
    result = rent_graph.invoke({"requirement": req})
    assert result["ranked"]
    for c in result["ranked"]:
        assert c.match_reasons


def test_area_filter() -> None:
    """面积硬条件过滤。"""
    req = RentRequirement(max_price=4000, district="滨湖", min_area=40, room_types=["1室"])
    result = rent_graph.invoke({"requirement": req})
    for c in result["ranked"]:
        assert c.area >= 40
