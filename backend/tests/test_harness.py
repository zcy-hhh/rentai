# 作者：zcy
"""Harness 治理测试（M6）：死循环护栏 + 上下文护栏 + SSE 流式端点。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.harness import ContextGuardError, guard_requirement, safe_stream
from app.main import app
from app.models.schemas import RentRequirement

client = TestClient(app)


def _req(**kw) -> RentRequirement:
    defaults = dict(district="新吴区", max_price=3000)
    defaults.update(kw)
    return RentRequirement(**defaults)


# ---------- 上下文护栏：输入边界 ----------

def test_guard_requirement_valid() -> None:
    guard_requirement(_req())  # 合法输入不抛异常


def test_guard_rejects_overlong_district() -> None:
    with pytest.raises(ContextGuardError):
        guard_requirement(_req(district="x" * 51))


def test_guard_rejects_too_many_tags() -> None:
    with pytest.raises(ContextGuardError):
        guard_requirement(_req(tags=[f"t{i}" for i in range(11)]))


def test_guard_rejects_excessive_price() -> None:
    # Pydantic 放行（>0），但 harness 策略上限 MAX_PRICE 拒绝
    with pytest.raises(ContextGuardError):
        guard_requirement(_req(max_price=200_000))


def test_guard_rejects_excessive_area() -> None:
    with pytest.raises(ContextGuardError):
        guard_requirement(_req(min_area=20_000))


# ---------- 流式编排（死循环护栏内部经 recursion_limit 守护） ----------

@pytest.mark.asyncio
async def test_safe_stream_yields_all_nodes() -> None:
    events = []
    async for e in safe_stream(_req()):
        events.append(e)
    nodes = [k for ev in events for k in ev]
    for expected in ("retrieve", "filter", "rank", "risk_check", "build_list"):
        assert expected in nodes


# ---------- SSE 端点 ----------

def test_sse_stream_returns_event_stream() -> None:
    r = client.post(
        "/api/rent/search/stream", json={"district": "新吴区", "max_price": 3000}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    for expected in ("event: retrieve", "event: filter", "event: risk_check", "event: build_list"):
        assert expected in r.text


def test_sse_stream_rejects_invalid_input() -> None:
    r = client.post(
        "/api/rent/search/stream", json={"district": "x" * 51, "max_price": 3000}
    )
    assert r.status_code == 422


def test_search_uses_guardrail() -> None:
    r = client.post("/api/rent/search", json={"district": "x" * 51, "max_price": 3000})
    assert r.status_code == 422
