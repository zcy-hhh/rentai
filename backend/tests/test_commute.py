# 作者：zcy
"""M3 测试：通勤测算（可插拔 commutator）接入排序。"""
from __future__ import annotations

from app.agents.graph import rent_graph
from app.models.schemas import RentRequirement
from app.tools.commute import get_commutator


def test_commutator_returns_reasonable_time() -> None:
    c = get_commutator()
    m = c.estimate_minutes("滨湖区湖滨路", "高新区软件园", True)
    assert 0 < m < 60


def test_commute_filled_on_candidate() -> None:
    r = rent_graph.invoke(
        {"requirement": RentRequirement(max_price=6000, district="滨湖", room_types=["1室", "2室"], commute_to="高新区软件园")}
    )
    assert any(c.commute_minutes is not None for c in r["ranked"])


def test_commute_penalty_when_exceeds_cap() -> None:
    r = rent_graph.invoke(
        {"requirement": RentRequirement(max_price=6000, district="惠山", room_types=["1室", "2室"], commute_to="高新区软件园", commute_max_minutes=5)}
    )
    reasons = [reason for c in r["ranked"] for reason in c.match_reasons if "超出上限" in reason]
    assert reasons


def test_commute_bonus_when_within_cap() -> None:
    r = rent_graph.invoke(
        {"requirement": RentRequirement(max_price=6000, district="滨湖", room_types=["1室", "2室"], commute_to="高新区软件园", commute_max_minutes=60)}
    )
    reasons = [reason for c in r["ranked"] for reason in c.match_reasons if "可接受范围" in reason]
    assert reasons
