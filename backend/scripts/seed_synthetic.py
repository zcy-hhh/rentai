# 作者：zcy
"""灌入合成房源向量：合成文本 → 百炼 embedding(1024) → pgvector listings 表。

用法：uv run python scripts/seed_synthetic.py
- 200 套合成房源，真实调用百炼 embedding（自动分批 10，约 20 次调用）。
- 失败则零向量占位（不阻塞）；幂等（按 id upsert）。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Listing
from app.db.session import SessionLocal
from app.llm import client as llm
from scripts.synthetic_data import generate_synthetic


async def main() -> None:
    data = generate_synthetic(200)
    texts = [
        f"{d['title']}，{d['district']}区，{d['address']}，{d['description']}"
        for d in data
    ]
    try:
        embs = await llm.embed_texts(texts)  # 自动分批 10
        print(f"[seed] 百炼真实生成 {len(embs)} 条向量（1024 维），共 {len(texts) // 10 + 1} 批调用")
    except Exception as e:
        print(f"[seed] 向量生成失败，用零向量占位：{e}")
        embs = [[0.0] * 1024 for _ in texts]

    async with SessionLocal() as s:
        for d, emb in zip(data, embs):
            stmt = pg_insert(Listing).values(
                id=d["id"], title=d["title"], source=d["source"], url=d["url"],
                district=d["district"], address=d["address"], price=d["price"],
                area=d["area"], room_type=d["room_type"], orientation=d["orientation"],
                floor=d["floor"], facilities=d["facilities"], listing_date=d["listing_date"],
                is_verified=d["is_verified"], risk_flags=d["risk_flags"], description=d["description"],
                embedding=emb,
            ).on_conflict_do_update(
                index_elements=[Listing.id],
                set_={"embedding": emb, "price": d["price"], "title": d["title"],
                      "is_verified": d["is_verified"], "risk_flags": d["risk_flags"],
                      "description": d["description"]},
            )
            await s.execute(stmt)
        await s.commit()
        total = (await s.execute(select(Listing).where(Listing.source == "synthetic"))).scalars().all()
        all_n = (await s.execute(select(Listing.id))).scalars().all()
        print(f"[seed] 已写入 {len(total)} 套合成房源；库内房源总数：{len(all_n)}")


if __name__ == "__main__":
    asyncio.run(main())
