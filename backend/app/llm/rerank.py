# 作者：zcy
"""rerank 精排：阿里云百炼 gte-rerank（DashScope 原生端点）。

OpenAI 兼容模式没有标准 rerank 端点，走 DashScope 原生
`/api/v1/services/rerank/text-rerank/text-rerank`。
返回按 query 相关性降序的原始文档索引，供检索层重排候选。
"""
from __future__ import annotations

import httpx

from app.core.config import settings

_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


async def rerank(query: str, documents: list[str], top_n: int = 30) -> list[int]:
    """对 documents 按 query 相关性重排，返回降序的原始文档索引。

    失败抛异常（调用方决定是否降级跳过 rerank）。
    """
    if not documents:
        return []
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
        "return_documents": False,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _RERANK_URL,
            headers={
                "Authorization": f"Bearer {settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    ordered = sorted(
        results, key=lambda r: r.get("relevance_score", 0.0), reverse=True
    )
    return [r["index"] for r in ordered]
