# 作者：zcy
"""数据库种子：建表 + 迁移 18 套 mock 房源（含 pgvector 向量）+ demo 用户。

用法：uv run python -m app.db.seed
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, text

from app.core.users import DEMO_USERS
from app.db.mock_listings import MOCK_LISTINGS
from app.db.models import Base, Listing, User
from app.db.session import SessionLocal, engine
from app.llm import client as llm


async def _seed_listings() -> None:
    async with SessionLocal() as s:
        existing = (await s.execute(select(Listing.id))).scalars().all()
        if existing:
            print(f"[seed] 已有 {len(existing)} 套房源，跳过")
            return
        texts = [
            f"{l['title']}，{l['district']}区，{l['address']}，{l['description']}"
            for l in MOCK_LISTINGS
        ]
        try:
            embs = await llm.embed_texts(texts)
            print(f"[seed] 已用百炼生成 {len(embs)} 条向量（1024 维）")
        except Exception as e:  # 控制用量：失败则用零向量占位，不阻塞建表
            print(f"[seed] 向量生成失败，用零向量占位：{e}")
            embs = [[0.0] * 1024 for _ in texts]
        for i, l in enumerate(MOCK_LISTINGS):
            s.add(
                Listing(
                    id=l["id"], title=l["title"], source=l["source"], url=l["url"],
                    district=l["district"], address=l["address"], price=l["price"],
                    area=l["area"], room_type=l["room_type"], orientation=l["orientation"],
                    floor=l["floor"], facilities=l["facilities"],
                    listing_date=l["listing_date"], is_verified=l["is_verified"],
                    risk_flags=l["risk_flags"], description=l["description"],
                    embedding=embs[i],
                )
            )
        await s.commit()
        print(f"[seed] 已写入 {len(MOCK_LISTINGS)} 套房源")


async def _seed_users() -> None:
    async with SessionLocal() as s:
        existing = (await s.execute(select(User.username))).scalars().all()
        if existing:
            print("[seed] 已有用户，跳过")
            return
        # 注意：演示用户明文存密码便于联调；生产必须 bcrypt hash（见开发记录安全项）
        for u in DEMO_USERS.values():
            s.add(
                User(username=u.username, password_hash=u.password,
                     role=u.role, tenant_id=u.tenant_id)
            )
        await s.commit()
        print(f"[seed] 已写入 {len(DEMO_USERS)} 个用户")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        print("[seed] 建表完成")
    await _seed_listings()
    await _seed_users()


if __name__ == "__main__":
    asyncio.run(main())
