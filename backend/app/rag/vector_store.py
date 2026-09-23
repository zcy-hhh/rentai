# 作者：zcy
"""向量存储抽象：生产用 pgvector，开发用内存实现（可插拔）。

按 Dify RAG 管道分阶段思想，把"存储/检索"从业务逻辑解耦。
M2 先用内存实现跑通；M5b 接入 pgvector（PostgreSQL+pgvector，HNSW 索引）。
"""
from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

from sqlalchemy import text

from app.db.session import SessionLocal


@runtime_checkable
class VectorStore(Protocol):
    """向量存储协议。"""

    def add(self, text: str, embedding: list[float], meta: dict) -> str: ...

    def search(self, embedding: list[float], top_k: int = 5) -> list[dict]: ...


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """开发/测试用的内存向量库（余弦相似度）。生产用 PgVectorStore 替换。"""

    def __init__(self) -> None:
        self._items: list[tuple[str, list[float], dict]] = []

    def add(self, text: str, embedding: list[float], meta: dict) -> str:
        idx = str(len(self._items))
        self._items.append((text, embedding, {**meta, "text": text, "id": idx}))
        return idx

    def search(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        scored = [(_cosine(embedding, emb), meta) for _, emb, meta in self._items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(meta, score=round(s, 4)) for s, meta in scored[:top_k]]


# M5b 接入 pgvector：真实向量检索（HNSW 索引加速，余弦相似度）
class PgVectorStore:
    """PostgreSQL + pgvector 持久化向量库。embedding 存 listings.embedding(VECTOR(1024))。"""

    def __init__(self, session_factory=None) -> None:
        self._sf = session_factory or SessionLocal

    @staticmethod
    def _to_vector_str(embedding: list[float]) -> str:
        return "[" + ",".join(str(x) for x in embedding) + "]"

    async def search(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        q = text(
            """
            SELECT id, title, district, price, area, description,
                   1 - (embedding <=> CAST(:q AS vector)) AS score
            FROM listings
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :k
            """
        )
        async with self._sf() as s:
            rows = (await s.execute(q, {"q": self._to_vector_str(embedding), "k": top_k})).all()
        return [dict(r._mapping, score=round(float(r._mapping["score"]), 4)) for r in rows]
