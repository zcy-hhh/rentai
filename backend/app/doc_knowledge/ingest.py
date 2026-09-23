# 作者：zcy
"""文档入库：解析 → 切块 → embedding → 写入 doc_chunks（pgvector）。

复用百炼 text-embedding-v4（1024 维，单批≤10 自动分批），
doc_id 唯一标识一次入库，可重复入库（覆盖式：先清旧 chunk）。
"""
from __future__ import annotations

import uuid

from app.db.models import DocChunk
from app.db.session import SessionLocal
from app.doc_knowledge.chunker import chunk_document
from app.doc_knowledge.parser import extract_text
from app.llm import client as llm


def _vec_str(v: list[float]) -> str:
    return "[" + ",".join(str(x) for x in v) + "]"


async def ingest_document(path: str, filename: str, doc_id: str | None = None) -> dict:
    """解析文档并入库，返回 {doc_id, chunks, source_name}。"""
    pages = extract_text(path, filename)
    if not pages:
        raise ValueError(f"{filename} 未解析出文本（可能是扫描件，暂不支持）")

    chunks = chunk_document(pages)
    texts = [c["text"] for c in chunks]
    embeddings = await llm.embed_texts(texts)  # 分批，单批≤10

    doc_id = doc_id or uuid.uuid4().hex
    rows = [
        DocChunk(
            doc_id=doc_id,
            source_name=filename,
            page=c["page"],
            chunk_index=c["chunk_index"],
            text=c["text"],
            embedding=embeddings[i],
            meta={"sheet": c.get("sheet")} if c.get("sheet") else {},
        )
        for i, c in enumerate(chunks)
    ]

    async with SessionLocal() as s:
        # 覆盖式入库：同 doc_id 先清旧块，避免重复累积
        from sqlalchemy import delete

        await s.execute(delete(DocChunk).where(DocChunk.doc_id == doc_id))
        s.add_all(rows)
        await s.commit()

    return {"doc_id": doc_id, "chunks": len(chunks), "source_name": filename}
