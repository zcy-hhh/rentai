# 作者：zcy
"""看房清单服务：HITL 状态管理（pending/confirmed/adjusted）+ 审计留痕。

M2 用内存存储；M5 迁移到 PostgreSQL 持久化。
"""
from __future__ import annotations

from app.db.models import Viewing
from app.db.session import SessionLocal
from app.models.schemas import ViewingList


class ViewingListStore:
    def __init__(self) -> None:
        self._store: dict[str, ViewingList] = {}
        self._audit: list[dict] = []

    def save(self, vl: ViewingList) -> ViewingList:
        self._store[vl.list_id] = vl
        return vl

    def get(self, list_id: str) -> ViewingList | None:
        return self._store.get(list_id)

    def confirm(self, list_id: str, action: str, note: str) -> ViewingList | None:
        vl = self._store.get(list_id)
        if vl is None:
            return None
        vl.status = "confirmed" if action == "confirm" else "adjusted"
        self._audit.append({"list_id": list_id, "action": action, "note": note})  # 审计留痕
        return vl


viewing_store = ViewingListStore()


class PgViewingListStore:
    """PostgreSQL 持久化的看房清单存储（M6）。

    与内存 store 同构（save/get/confirm），可插拔替换；ViewingList 完整数据
    落 `viewings.payload`，重启不丢。HITL 状态机持久化 = 企业级底线。
    """

    async def save(self, vl: ViewingList, user_id: str = "demo") -> ViewingList:
        async with SessionLocal() as session:
            session.add(
                Viewing(
                    id=vl.list_id,
                    user_id=user_id,
                    listing_ids=[c.id for c in vl.candidates],
                    status=vl.status,
                    note="",
                    payload=vl.model_dump(),
                )
            )
            await session.commit()
            return vl

    async def get(self, list_id: str) -> ViewingList | None:
        async with SessionLocal() as session:
            row = await session.get(Viewing, list_id)
            if row is None:
                return None
            payload = dict(row.payload)
            payload["status"] = row.status  # 以行状态为准（payload 可能滞后）
            return ViewingList(**payload)

    async def confirm(self, list_id: str, action: str, note: str) -> ViewingList | None:
        async with SessionLocal() as session:
            row = await session.get(Viewing, list_id)
            if row is None:
                return None
            new_status = "confirmed" if action == "confirm" else "adjusted"
            row.status = new_status
            row.note = note
            # 同步 payload 中的状态，保证 get 读到最新状态
            row.payload = {**row.payload, "status": new_status}
            await session.commit()
            return ViewingList(**row.payload)


pg_viewing_store = PgViewingListStore()
