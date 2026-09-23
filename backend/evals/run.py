# 作者：zcy
"""评测 runner：计算匹配准确率 / 召回率、避坑召回率（M4）。

用法：uv run python evals/run.py  （输出 JSON 指标）
指标：
- match_precision@k：返回候选里"应命中"的占比（Top-K 精确率）
- match_recall：应命中房源中被返回的占比
- risk_recall：坑房源被标注出"应命中风险"的占比
"""
from __future__ import annotations

import json

from app.agents.graph import rent_graph
from app.db.mock_listings import MOCK_LISTINGS
from app.tools.listing_source import MockListingSource
from app.models.schemas import Listing, RentRequirement
from app.rag.knowledge_base import check_listing

from evals.dataset import MATCH_CASES, RISK_CASES

_LOCKUP = {r["id"]: r for r in MOCK_LISTINGS}


def _run_match_case(case: dict, sources: list) -> tuple[set[str], set[str]]:
    """在指定数据源池上跑匹配（限定池子，保证机制自洽 1.0 可校验）。"""
    req = RentRequirement(**case["requirement"])
    from app.agents.nodes import node_filter, node_rank

    raw = [lst for src in sources for lst in src.search(req)]
    state: dict = {"requirement": req, "raw": raw}
    state.update(node_filter(state))
    state.update(node_rank(state))
    returned = {c.id for c in state["ranked"]}
    expected = set(case["expected"])
    return returned, expected


def run_eval(sources: list | None = None) -> dict:
    # 1) 匹配准确率 / 召回率（默认 mock-only 池，机制自洽）
    sources = sources or [MockListingSource()]
    precisions, recalls = [], []
    for case in MATCH_CASES:
        returned, expected = _run_match_case(case, sources)
        hit = returned & expected
        precision = len(hit) / len(returned) if returned else 0.0
        recall = len(hit) / len(expected) if expected else 0.0
        precisions.append(precision)
        recalls.append(recall)

    # 2) 避坑召回率
    risk_recalls = []
    for case in RISK_CASES:
        listing = Listing(**_LOCKUP[case["listing_id"]])
        detected = {r.kind for r in check_listing(listing)}
        expected = set(case["expected_risks"])
        hit = detected & expected
        risk_recalls.append(len(hit) / len(expected) if expected else 0.0)

    return {
        "match_cases": len(MATCH_CASES),
        "match_precision@k": round(sum(precisions) / len(precisions), 3),
        "match_recall": round(sum(recalls) / len(recalls), 3),
        "risk_cases": len(RISK_CASES),
        "risk_recall": round(sum(risk_recalls) / len(risk_recalls), 3),
    }


if __name__ == "__main__":
    print(json.dumps(run_eval(), ensure_ascii=False, indent=2))
