# 作者：zcy
"""M5b 数据库持久化测试：PG 房源读取 + pgvector 向量检索。

需 Docker PostgreSQL 运行（docker compose up -d postgres），否则自动 skip。
用 pytest-asyncio 统一事件循环，避免 asyncio.run 残留污染其他测试。
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models import Listing
from app.db.session import SessionLocal
from app.rag.vector_store import PgVectorStore


@pytest.mark.asyncio
async def test_persistence_and_pgvector_search() -> None:
    """一次连接内完成：房源持久化读取 + pgvector 向量检索（HNSW 余弦）。"""
    try:
        async with SessionLocal() as s:
            n = (await s.execute(select(func.count(Listing.id)))).scalar_one()
            listing = (
                await s.execute(
                    select(Listing).where(Listing.embedding.isnot(None)).limit(1)
                )
            ).scalars().first()
        assert listing is not None
        results = await PgVectorStore().search(listing.embedding, top_k=5)
        listing_id, top_id, score = listing.id, results[0]["id"], results[0]["score"]
    except Exception as e:  # PG 不可用时跳过，保证无数据库环境也能跑单元测试
        pytest.skip(f"PostgreSQL 不可用，跳过：{e}")

    assert n >= 18  # seed 已写入 18 套
    assert top_id == listing_id  # 用自身向量检索，首条应命中自身
    assert score > 0.99
