# 作者：zcy
"""混合检索（关键词 ∪ 语义，可 rerank）——检索层真正接入大模型（M9）。

- 关键词：现有数据源（mock + 合成）粗筛，稳定可复现。
- 语义：需求文本 → 百炼 embedding → pgvector 余弦召回 TopK。
- rerank：gte-rerank 对合并候选重排（可选，失败自动跳过）。

任一层失败都降级（不挂死），保证检索主链路可用。
"""
from __future__ import annotations

from functools import lru_cache

from app.db.mock_listings import MOCK_LISTINGS
from app.db.synthetic import generate_synthetic
from app.llm import client as llm
from app.models.schemas import Listing, RentRequirement
from app.rag.vector_store import PgVectorStore
from app.tools.listing_source import get_sources

SEMANTIC_TOP_K = 40  # 语义召回候选数


@lru_cache(maxsize=1)
def _all_by_id() -> dict[str, Listing]:
    """全量房源 id → Listing 映射（mock + 合成，218 套），供语义召回补全字段。"""
    out: dict[str, Listing] = {r["id"]: Listing(**r) for r in MOCK_LISTINGS}
    for d in generate_synthetic(200):
        out[d["id"]] = Listing(**d)
    return out


def req_text(req: RentRequirement) -> str:
    """把结构化需求转成语义检索文本。"""
    parts = [
        req.district or "",
        f"{int(req.max_price)}元以内",
        "/".join(req.room_types),
    ]
    if req.min_area:
        parts.append(f"至少{int(req.min_area)}平米")
    if req.commute_to:
        parts.append(f"通勤到{req.commute_to}")
    if req.tags:
        parts.append("、".join(req.tags))
    return " ".join(p for p in parts if p)


async def semantic_recall(req: RentRequirement, top_k: int = SEMANTIC_TOP_K) -> list[Listing]:
    """需求 embedding → pgvector 语义召回完整房源。失败返回 []（降级）。"""
    try:
        qvec = (await llm.embed_texts([req_text(req)]))[0]
    except Exception:
        return []
    try:
        rows = await PgVectorStore().search(qvec, top_k=top_k)
    except Exception:
        return []
    by_id = _all_by_id()
    out: list[Listing] = []
    for r in rows:
        lst = by_id.get(r["id"])
        if lst:
            out.append(lst)
    return out


async def hybrid_search(
    req: RentRequirement,
    use_semantic: bool = True,
    use_rerank: bool = True,
) -> list[Listing]:
    """混合检索：关键词召回 ∪ 语义召回，按 id 去重，可选 rerank 重排。"""
    merged: dict[str, Listing] = {}
    for src in get_sources():  # 关键词粗筛（mock + 合成）
        for lst in src.search(req):
            merged.setdefault(lst.id, lst)

    if use_semantic:
        for lst in await semantic_recall(req):  # 语义召回补入关键词没召回的
            merged.setdefault(lst.id, lst)

    items = list(merged.values())

    if use_rerank and len(items) > 1:
        try:
            from app.llm.rerank import rerank

            docs = [f"{l.title}，{l.district}，{l.description}" for l in items]
            order = await rerank(req_text(req), docs, top_n=min(30, len(items)))
            items = [items[i] for i in order]
        except Exception:
            pass  # rerank 失败降级：保持合并顺序
    return items
