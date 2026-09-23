# 作者：zcy
"""API 端点测试：验证 REST 入口与健康检查。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_rent_search_returns_candidates() -> None:
    payload = {"max_price": 4000, "district": "滨湖", "room_types": ["1室"]}
    r = client.post("/api/rent/search", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "candidates" in data
    assert data["total_matched"] == len(data["candidates"])
    # 每个候选可序列化且含理由
    for c in data["candidates"]:
        assert "match_score" in c
        assert c["match_reasons"]


def test_rent_search_validation() -> None:
    """缺失必填字段（max_price）应返回 422。"""
    r = client.post("/api/rent/search", json={"district": "滨湖"})
    assert r.status_code == 422


def test_viewing_list_hitl_flow() -> None:
    """生成看房清单 → HITL 确认闭环。"""
    payload = {"max_price": 4000, "district": "滨湖", "room_types": ["1室"]}
    r = client.post("/api/rent/viewing-list", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending"
    assert data["list_id"]
    assert data["verify_items"] or data["ask_items"]

    r2 = client.post("/api/rent/confirm", json={"list_id": data["list_id"], "action": "confirm"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "confirmed"


def test_confirm_missing_list_404() -> None:
    r = client.post("/api/rent/confirm", json={"list_id": "not-exist", "action": "confirm"})
    assert r.status_code == 404
