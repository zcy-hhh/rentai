# 作者：zcy
"""语义检索召回率评测（合成数据扩量后）。

对一组测试需求，用「需求文本 → 百炼 embedding → PgVectorStore 语义检索」取 Top-K，
真值(ground truth) = 硬条件规则标注（区 + 户型 + 价格预算 均匹配的合成房源），
计算不同 K 下的 召回率(recall@k) 与 精确率(precision@k)，用于量化检索效果。

说明：真值由确定性规则生成（与检索语义正交），用于"能看召回率"的量化闭环；
指标反映的是向量语义检索在合成数据上的表现，非效果天花板（同 M4 诚实口径）。
用法：uv run python scripts/run_synthetic_eval.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# 允许从 backend 根 import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.llm import client as llm
from app.rag.vector_store import PgVectorStore
from scripts.synthetic_data import generate_synthetic

# 测试需求集（区 / 户型 / 预算，需求文本尽量贴近自然检索表达）
TEST_REQS = [
    {"name": "梁溪·1室·预算3k", "district": "梁溪", "room": "1室", "budget": 3000,
     "query": "梁溪区 一室一厅 预算3000元左右 近地铁 精装"},
    {"name": "滨湖·2室·预算5k", "district": "滨湖", "room": "2室", "budget": 5000,
     "query": "滨湖区 两居室 预算5000元 电梯 精装 小区环境好"},
    {"name": "新吴·1室·预算2.5k", "district": "新吴", "room": "1室", "budget": 2500,
     "query": "新吴区 单间一居 预算2500元 近地铁 通勤方便"},
    {"name": "锡山·3室·预算6k", "district": "锡山", "room": "3室", "budget": 6000,
     "query": "锡山区 三居室 预算6000元 整租 家庭居住"},
    {"name": "惠山·2室·预算3.5k", "district": "惠山", "room": "2室", "budget": 3500,
     "query": "惠山区 两居室 预算3500元 性价比高 有燃气"},
]

K_VALUES = [1, 3, 5, 10, 20]


def ground_truth(req: dict) -> set[str]:
    """硬条件规则标注相关：区 + 户型 + 价格预算 均匹配的合成房源。"""
    data = generate_synthetic(200)
    return {
        d["id"] for d in data
        if d["district"] == req["district"]
        and d["room_type"] == req["room"]
        and d["price"] <= req["budget"]
    }


async def main() -> None:
    store = PgVectorStore(SessionLocal)
    # 每个 K 的指标聚合
    agg = {k: {"recall": [], "precision": []} for k in K_VALUES}
    per_case: list[dict] = []

    for req in TEST_REQS:
        emb = (await llm.embed_texts([req["query"]], batch_size=1))[0]  # 需求文本真实 embedding
        hits = await store.search(emb, top_k=K_VALUES[-1])  # 一次检索取最大 K，按 K 截断
        returned = {h["id"] for h in hits}
        truth = ground_truth(req)
        relevant = truth & returned  # 检索返回且相关
        case_row = {"name": req["name"], "truth_n": len(truth), "returned": len(returned)}
        for k in K_VALUES:
            top = {h["id"] for h in hits[:k]}
            hit_k = len(top & truth)
            recall = hit_k / len(truth) if truth else 0.0
            precision = hit_k / k if k else 0.0
            agg[k]["recall"].append(recall)
            agg[k]["precision"].append(precision)
            case_row[f"recall@{k}"] = round(recall, 3)
            case_row[f"precision@{k}"] = round(precision, 3)
        per_case.append(case_row)

    # 输出曲线数据（JSON）+ 人类可读摘要
    curve = [
        {"k": k, "avg_recall": round(sum(v["recall"]) / len(v["recall"]), 3),
         "avg_precision": round(sum(v["precision"]) / len(v["precision"]), 3)}
        for k, v in agg.items()
    ]
    result = {"cases": per_case, "curve": curve}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    with open(os.path.join(os.path.dirname(__file__), "synthetic_eval_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
