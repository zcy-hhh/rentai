# 作者：zcy
"""文档检索：query embedding → pgvector 余弦召回 → 带引用原文块。

返回 [{text, source_name, page, sheet, score}]，供回答引用（防幻觉）。
失败降级返回 []，不挂死主链路。
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal
from app.llm import client as llm

TOP_K = 5


def _vec_str(v: list[float]) -> str:
    return "[" + ",".join(str(x) for x in v) + "]"


async def search_docs(query: str, top_k: int = TOP_K) -> list[dict]:
    try:
        qv = (await llm.embed_texts([query]))[0]
    except Exception:
        return []

    q = text(
        """
        SELECT text, source_name, page, chunk_index, meta,
               1 - (embedding <=> CAST(:q AS vector)) AS score
        FROM doc_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:q AS vector)
        LIMIT :k
        """
    )
    try:
        async with SessionLocal() as s:
            rows = (await s.execute(q, {"q": _vec_str(qv), "k": top_k})).all()
    except Exception:
        return []

    out = []
    for r in rows:
        meta = dict(r._mapping["meta"] or {})
        out.append(
            {
                "text": r._mapping["text"],
                "source_name": r._mapping["source_name"],
                "page": r._mapping["page"],
                "sheet": meta.get("sheet"),
                "score": round(float(r._mapping["score"]), 4),
            }
        )
    return out
