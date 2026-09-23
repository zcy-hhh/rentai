# 作者：zcy
"""真实评测运行脚本：用20+条多样化用例跑出可信指标。"""
import sys
sys.path.insert(0, ".")
import asyncio
from app.models.schemas import RentRequirement
from app.tools.listing_source import get_sources
from app.agents.nodes import node_filter, node_rank, node_risk_check
from app.rag.retriever import retrieve_risks
from evals.dataset_v2 import MATCH_CASES, RISK_CASES, AGENT_DECISION_CASES


def ground_truth_filter(req: RentRequirement, listings):
    """独立 ground truth：硬条件过滤，和系统 node_filter 对比。"""
    result = []
    for l in listings:
        if l.price > req.max_price:
            continue
        if req.min_area is not None and l.area < req.min_area:
            continue
        if req.room_types and not any(rt in l.room_type for rt in req.room_types):
            continue
        if req.tags and not all(t in l.facilities for t in req.tags):
            continue
        if req.district and l.district != req.district:
            continue
        result.append(l)
    return result


def eval_matching():
    """匹配精确率/召回率评测。"""
    req_all = RentRequirement(max_price=99999)
    all_listings = []
    for src in get_sources():
        all_listings.extend(src.search(req_all))

    total_precision = 0
    total_recall = 0
    valid_cases = 0
    empty_cases_correct = 0
    empty_cases_total = 0
    details = []

    for case in MATCH_CASES:
        req = RentRequirement(**case["requirement"])
        # 模拟完整 pipeline：retrieve（含区域过滤）→ filter
        raw = []
        for src in get_sources():
            raw.extend(src.search(req))
        state = {"requirement": req, "raw": raw}
        filtered_state = node_filter(state)
        system_result = set(l.id for l in filtered_state["filtered"])
        # Ground truth（独立计算）
        gt_result = set(l.id for l in ground_truth_filter(req, all_listings))

        if len(gt_result) == 0:
            empty_cases_total += 1
            if len(system_result) == 0:
                empty_cases_correct += 1
            details.append(f"  [空结果] {case['name']}: GT=0, Sys={len(system_result)} {'✓' if len(system_result)==0 else '✗'}")
            continue

        # 精确率：系统返回中正确的比例
        tp = len(system_result & gt_result)
        precision = tp / len(system_result) if system_result else 0
        # 召回率：GT中被返回的比例
        recall = tp / len(gt_result) if gt_result else 0

        total_precision += precision
        total_recall += recall
        valid_cases += 1
        details.append(f"  {case['name']}: GT={len(gt_result)}, Sys={len(system_result)}, P={precision:.3f}, R={recall:.3f}")

    avg_precision = total_precision / valid_cases if valid_cases else 0
    avg_recall = total_recall / valid_cases if valid_cases else 0
    empty_acc = empty_cases_correct / empty_cases_total if empty_cases_total else 0

    print("=== 匹配评测（20条用例）===")
    for d in details:
        print(d)
    print(f"\n平均精确率: {avg_precision:.3f} ({valid_cases} 条非空用例)")
    print(f"平均召回率: {avg_recall:.3f}")
    print(f"空结果正确率: {empty_acc:.3f} ({empty_cases_correct}/{empty_cases_total})")
    return avg_precision, avg_recall, empty_acc


def eval_risk():
    """避坑召回率评测。"""
    req_all = RentRequirement(max_price=99999)
    all_listings = []
    for src in get_sources():
        all_listings.extend(src.search(req_all))
    listing_map = {l.id: l for l in all_listings}

    # 计算各区域均价
    from collections import defaultdict
    district_prices = defaultdict(list)
    for l in all_listings:
        district_prices[l.district].append(l.price)
    district_avg = {d: sum(v)/len(v) for d, v in district_prices.items()}

    total_recall = 0
    valid = 0
    details = []

    for case in RISK_CASES:
        lid = case["listing_id"]
        if lid not in listing_map:
            details.append(f"  [跳过] {case['name']}: 房源 {lid} 不存在")
            continue
        listing = listing_map[lid]
        avg = district_avg.get(listing.district)
        risks = retrieve_risks(listing, district_avg_price=avg)
        risk_kinds = set(r.kind for r in risks)
        expected = set(case["expected_risks"])
        hit = len(risk_kinds & expected)
        recall = hit / len(expected) if expected else 0
        total_recall += recall
        valid += 1
        details.append(f"  {case['name']}({lid}): 期望={expected}, 命中={risk_kinds & expected}, 全部={risk_kinds}, R={recall:.3f}")

    avg_recall = total_recall / valid if valid else 0
    print("\n=== 避坑评测（6条用例）===")
    for d in details:
        print(d)
    print(f"\n平均避坑召回率: {avg_recall:.3f} ({valid} 条有效用例)")
    return avg_recall


async def eval_agent_decisions():
    """Agent 决策质量评测。"""
    from app.agents.conversational import chat_step

    total_score = 0
    details = []
    for case in AGENT_DECISION_CASES:
        history = case.get("history", [])
        result = await chat_step("eval-user", "eval-session", case["message"], history=history)
        kind = result.get("kind")
        expected = case["expected_kind"]
        correct = kind == expected
        score = 1.0 if correct else 0.0
        # 部分分：clarify 和 message 混淆给0.5
        if not correct and {kind, expected} <= {"clarify", "message"}:
            score = 0.5
        total_score += score
        details.append(f"  {case['name']}: 期望={expected}, 实际={kind}, 分={score:.1f}")

    avg_score = total_score / len(AGENT_DECISION_CASES)
    print("\n=== Agent决策评测（8条用例）===")
    for d in details:
        print(d)
    print(f"\n平均决策质量: {avg_score:.3f}")
    return avg_score


async def main():
    print("RentAI 真实评测（基于235套房源，34条用例）")
    print("=" * 50)
    p, r, empty_acc = eval_matching()
    risk_r = eval_risk()
    agent_score = await eval_agent_decisions()

    print("\n" + "=" * 50)
    print("汇总:")
    print(f"  匹配精确率 match_precision@k: {p:.3f}")
    print(f"  匹配召回率 match_recall: {r:.3f}")
    print(f"  空结果处理正确率: {empty_acc:.3f}")
    print(f"  避坑召回率 risk_recall: {risk_r:.3f}")
    print(f"  Agent决策质量: {agent_score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
