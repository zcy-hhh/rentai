# -*- coding: utf-8 -*-
# 作者：zcy
"""Agent 级评测：工具选择 / 决策质量（能力地图黄区缺失项之一）。

区别于 M4 的"结果质量"评测（match_precision@k / recall / risk_recall），这里评测 **Agent 决策过程本身**：
- 是否覆盖全部核心工具（检索→过滤→评分→避坑→清单）
- 工具相对调用顺序是否正确（search 先、build 最后）
- 是否重复调用（浪费/死循环迹象）
- 是否尊重用户自由指令（如"不用查风险"时正确跳过 check_risks——体现模型自主决策）

零成本、可复现（基于 trace 判定）。样例含一次真实百炼执行产生的 trace。
"""
from __future__ import annotations

CORE = ["search_listings", "filter_hard", "score_rank", "check_risks", "build_viewing_list"]

# 评测样例（trace 为工具序列；来源含真实百炼执行 + 构造反例）
CASES = [
    {
        "name": "完整流程（真实百炼·滨湖3000近地铁）",
        "trace": ["search_listings", "filter_hard", "score_rank", "check_risks", "build_viewing_list"],
        "expect": {"skip_risk": False},
    },
    {
        "name": "用户免检风险（自主跳过 check_risks）",
        "trace": ["search_listings", "filter_hard", "score_rank", "build_viewing_list"],
        "expect": {"skip_risk": True},
    },
    {
        "name": "工具乱序（rank 在 filter 之前）",
        "trace": ["search_listings", "score_rank", "filter_hard", "check_risks", "build_viewing_list"],
        "expect": {"skip_risk": False},
    },
    {
        "name": "重复调用（search 两次，浪费/死循环隐患）",
        "trace": ["search_listings", "search_listings", "filter_hard", "score_rank", "check_risks", "build_viewing_list"],
        "expect": {"skip_risk": False},
    },
]


def _criteria(tools: list[str], expect: dict) -> list[tuple[str, bool]]:
    res: list[tuple[str, bool]] = []
    skip = expect.get("skip_risk", False)
    if not skip:
        res.append(("覆盖全部核心工具", all(t in tools for t in CORE)))
    else:
        res.append(("尊重用户指令-跳过check_risks", "check_risks" not in tools))
    # 按 trace 实际出现顺序取核心工具（而非 CORE 定义顺序），才能检出乱序
    present = [t for t in tools if t in CORE]
    idxs = [CORE.index(t) for t in present]
    # 相对顺序正确 = 在 CORE 中的索引严格递增（且不重复）
    order_ok = idxs == sorted(idxs) and len(idxs) == len(set(idxs))
    res.append(("核心工具相对顺序正确", order_ok))
    res.append(("无重复调用", len(tools) == len(set(tools))))
    return res


def evaluate_agent_decisions(cases: list[dict] | None = None) -> dict:
    cases = cases or CASES
    detail = []
    for case in cases:
        criteria = _criteria(case["trace"], case["expect"])
        passed = sum(1 for _, ok in criteria if ok)
        score = round(passed / len(criteria) * 100)
        detail.append({
            "name": case["name"],
            "trace": case["trace"],
            "score": score,
            "criteria": [{"name": n, "pass": ok} for n, ok in criteria],
        })
    avg = round(sum(d["score"] for d in detail) / len(detail), 1) if detail else 0.0
    return {"avg_decision_score": avg, "cases": detail}


if __name__ == "__main__":
    import json

    out = evaluate_agent_decisions()
    print("Agent 级决策质量均分:", out["avg_decision_score"], "/ 100")
    for c in out["cases"]:
        marks = "".join("✓" if k["pass"] else "✗" for k in c["criteria"])
        print(f"  {c['name']}: {c['score']} 分 [{marks}] trace={c['trace']}")
    print(json.dumps(out, ensure_ascii=False))
