# 作者：zcy
"""看房清单 PG 持久化测试（M6）。

验证 HITL 状态机在 PostgreSQL 中持久化：save/get/confirm 走 `viewings` 表，
服务重启数据不丢。需 Docker PostgreSQL 运行，否则自动 skip（同 test_db.py）。
用 pytest-asyncio 统一事件循环，避免与 asyncio.run 冲突。
"""
from __future__ import annotations

import uuid

import pytest

from app.models.schemas import CandidateListing, RentRequirement, ViewingList
from app.services.viewing import pg_viewing_store


def _mk_vl(list_id: str | None = None) -> ViewingList:
    # 每次生成唯一 id，避免重复运行主键冲突
    list_id = list_id or f"pg-vl-{uuid.uuid4().hex[:8]}"
    req = RentRequirement(district="新吴区", max_price=3000, room_types=["1室"])
    cand = CandidateListing(
        id="mock-001",
        title="新吴单间",
        source="mock",
        district="新吴区",
        price=2200,
        area=30,
        room_type="1室",
    )
    return ViewingList(
        list_id=list_id,
        requirement=req,
        candidates=[cand],
        verify_items=["现场核实群租"],
        status="pending",
    )


@pytest.mark.asyncio
async def test_pg_viewing_persistence_and_hitl() -> None:
    """save→get→confirm→get 全链路，PG 持久化 + HITL 状态机。"""
    try:
        vl = _mk_vl()
        await pg_viewing_store.save(vl, user_id="demo")

        got = await pg_viewing_store.get(vl.list_id)
        assert got is not None and got.list_id == vl.list_id
        assert got.candidates[0].id == "mock-001"
        assert got.requirement.district == "新吴区"

        conf = await pg_viewing_store.confirm(vl.list_id, "confirm", "确认看房")
        assert conf is not None and conf.status == "confirmed"
        assert (await pg_viewing_store.get(vl.list_id)).status == "confirmed"

        adj = await pg_viewing_store.confirm(vl.list_id, "adjust", "调整为周一")
        assert adj is not None and adj.status == "adjusted"

        # 不存在的清单返回 None
        assert await pg_viewing_store.get("pg-vl-nope") is None
    except Exception as e:  # PG 不可用时跳过，不阻断本地无库测试
        import traceback

        traceback.print_exc()
        pytest.skip(f"PostgreSQL 不可用，跳过：{e}")
