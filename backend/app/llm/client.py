# 作者：zcy
"""统一 LLM 网关：阿里云百炼（OpenAI 兼容），封装 chat / embedding / rerank。

设计思想（参考 Dify 的模型层解耦）：业务只依赖本模块，不直接碰 SDK，
便于后续替换模型/加缓存/加降级。
"""
from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )
    return _client


def is_configured() -> bool:
    return bool(settings.dashscope_api_key)


async def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    """批量生成向量（text-embedding-v4，1024 维）。百炼单批上限 10 条，自动分批。注意控制用量。"""
    if not is_configured():
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")
    client = get_client()
    result: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=1024,
        )
        result.extend(d.embedding for d in resp.data)
    return result


async def chat(
    messages: list[dict],
    temperature: float = 0.5,
    max_tokens: int = 1024,
) -> str:
    """对话补全（qwen-plus）。"""
    if not is_configured():
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""
