# 作者：zcy
"""Ragas 语义评测（用现成开源库 ragas 0.2.15，不手写指标）。

对标注的匹配用例跑混合检索 → 构造 RAG 样本（问题/检索上下文/答案/参考答案）→
ragas.evaluate 用百炼 qwen 判断两个语义指标：
- faithfulness：答案是否忠实于检索上下文（防幻觉）
- context_precision（LLMContextPrecisionWithoutReference）：检索上下文与需求的相关精确度
（已移除 response_relevancy：其"LLM 生成问题→Pydantic 严格 JSON 校验"步骤对百炼 qwen 的中文
宽松 JSON 输出不稳定，多次实测为 NaN；保留前两个对中文可稳定出值的指标。）

用法：uv run python evals/ragas_eval.py
注意：样本构造（hybrid_search 是 async）用 asyncio.run；evaluate 是同步函数，
必须在无 running loop 的同步上下文调用（否则 asyncio.timeout 找不到 task 报错）。
"""
from __future__ import annotations

import asyncio
import contextlib
import json

# ragas 0.2 在当前 Python 的 asyncio.timeout 兼容补丁：
# asyncio.timeout() 在 3.11+ 必须在 task 上下文中，而 ragas 部分路径在非 task 上下文调用会抛
# "Timeout should be used inside a task"。补丁在无 task 时退化为不超时（不报错），有 task 时保持原语义。
_orig_timeout = asyncio.timeout


@contextlib.asynccontextmanager
async def _timeout_compat(delay):
    if asyncio.current_task() is None:
        yield
    else:
        async with _orig_timeout(delay):
            yield


asyncio.timeout = _timeout_compat

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

from app.core.config import settings
from app.db.mock_listings import MOCK_LISTINGS
from app.models.schemas import RentRequirement
from app.rag.hybrid_retriever import hybrid_search, req_text

from evals.dataset import MATCH_CASES

_LOCKUP = {r["id"]: r for r in MOCK_LISTINGS}

METRICS = [
    Faithfulness(),
    LLMContextPrecisionWithoutReference(),
]


def _build_sample(case: dict, items: list) -> SingleTurnSample:
    req = RentRequirement(**case["requirement"])
    contexts = [f"{l.title}，{l.district}，¥{l.price}/月，{l.area}㎡，{l.description}" for l in items[:5]]
    top = items[0] if items else None
    response = (
        f"为你找到 {len(items)} 套候选，首套 {top.title}·{top.district} ¥{top.price}"
        f"（{top.area}㎡，{top.room_type}）。"
        if top else "未匹配到符合条件的房源。"
    )
    ref_texts = [
        f"{_LOCKUP[i]['title']}，{_LOCKUP[i]['district']}，¥{_LOCKUP[i]['price']}/月，{_LOCKUP[i]['area']}㎡"
        for i in case["expected"]
    ]
    reference = "；".join(ref_texts) if ref_texts else response
    return SingleTurnSample(
        user_input=req_text(req),
        retrieved_contexts=contexts,
        response=response,
        reference=reference,
    )


async def _collect_samples(limit: int) -> list[SingleTurnSample]:
    """async 构造样本（hybrid_search 是 async）。"""
    samples = []
    for case in MATCH_CASES[:limit]:
        req = RentRequirement(**case["requirement"])
        items = await hybrid_search(req)
        samples.append(_build_sample(case, items))
    return samples


def run_ragas_eval(limit: int = 3) -> dict:
    """跑 ragas 语义评测（evaluate 为同步函数，须在无 running loop 的上下文调用）。"""
    chat = ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        temperature=0,
    )
    emb = OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
    )

    samples = asyncio.run(_collect_samples(limit))
    dataset = EvaluationDataset(samples=samples)
    result = evaluate(dataset=dataset, metrics=METRICS, llm=chat, embeddings=emb)

    scores = result.scores if hasattr(result, "scores") else getattr(result, "df", None)
    out: dict[str, object] = {}
    if isinstance(scores, list):  # 0.2：每样本一个 dict
        from collections import defaultdict

        agg: dict[str, list] = defaultdict(list)
        for row in scores:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if v is not None:
                    try:
                        agg[k].append(float(v))
                    except (TypeError, ValueError):
                        pass
        out = {k: round(sum(v) / len(v), 3) for k, v in agg.items() if v}
    elif scores is not None:  # DataFrame
        for col in scores.columns:
            name = str(col)
            try:
                out[name] = round(float(scores[name].mean()), 3)
            except Exception:
                out[name] = None
    return {
        **out,
        "cases": limit,
        "note": "语义指标由 ragas(现成库 0.2.15) + 百炼 qwen 判断；值域通常 0~1。",
    }


if __name__ == "__main__":
    print(json.dumps(run_ragas_eval(), ensure_ascii=False, indent=2))
