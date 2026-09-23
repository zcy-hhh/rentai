# 作者：zcy
"""综合量化测试：多轮对话 + 双模式延迟对比 + 增量执行 token 节省 + 确定性评测。
运行：cd backend && uv run python evals/quant_test.py
"""
from __future__ import annotations

import asyncio
import json
import time

from app.agents.graph import rent_graph
from app.agents.conversational import chat_step
from app.agents.reflexion import run_with_reflexion
from app.models.schemas import RentRequirement
from evals.run import run_eval


async def test_pipeline_latency():
    """确定性管道延迟（5次取平均）。"""
    req = RentRequirement(district="滨湖", max_price=4000, room_types=["1室"])
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        state = await rent_graph.ainvoke({"requirement": req})
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "pipeline_latency_ms_avg": round(sum(times) / len(times), 0),
        "pipeline_latency_ms_all": [round(t, 0) for t in times],
        "candidates": len(state["viewing_list"].candidates),
    }


async def test_react_latency():
    """ReAct 自主决策延迟（3次取平均）。"""
    req = RentRequirement(district="滨湖", max_price=5000, room_types=["1室", "2室"])
    times = []
    reflexion_rounds = []
    for _ in range(3):
        t0 = time.perf_counter()
        trace, viewing, reflexion = await run_with_reflexion(req)
        times.append((time.perf_counter() - t0) * 1000)
        reflexion_rounds.append(len(reflexion))
    return {
        "react_latency_ms_avg": round(sum(times) / len(times), 0),
        "react_latency_ms_all": [round(t, 0) for t in times],
        "reflexion_rounds_avg": round(sum(reflexion_rounds) / len(reflexion_rounds), 1),
    }


async def test_multi_turn_dialogue():
    """多轮对话测试：闲聊 → 澄清 → 执行 → 增量修改。"""
    uid = "test_user_001"
    sid = "test_session_quant"
    turns = []

    # 第1轮：闲聊
    t0 = time.perf_counter()
    r1 = await chat_step(uid, sid, "你好，你能帮我做什么？")
    turns.append({"turn": 1, "type": "chat", "kind": r1["kind"], "latency_ms": round((time.perf_counter() - t0) * 1000, 0)})

    # 第2轮：模糊需求（应该触发澄清）
    t0 = time.perf_counter()
    r2 = await chat_step(uid, sid, "我想租个房子")
    turns.append({"turn": 2, "type": "vague", "kind": r2["kind"], "latency_ms": round((time.perf_counter() - t0) * 1000, 0)})

    # 第3轮：补充需求（应该执行）
    t0 = time.perf_counter()
    r3 = await chat_step(uid, sid, "滨湖区，预算3500以内，要1室的，近地铁")
    turns.append({"turn": 3, "type": "execute", "kind": r3["kind"], "latency_ms": round((time.perf_counter() - t0) * 1000, 0),
                   "candidates": len(r3.get("viewing", {}).get("candidates", [])) if r3.get("viewing") else 0,
                   "mode": r3.get("requirement", {}).get("user_note", "n/a")})

    # 第4轮：增量修改（在之前基础上加条件）
    history = [
        ("user", "滨湖区，预算3500以内，要1室的，近地铁"),
        ("assistant", r3.get("text", "") or "已为你找到候选房源"),
    ]
    t0 = time.perf_counter()
    r4 = await chat_step(uid, sid, "把预算提到4500，再看看有没有2室的", history=history)
    turns.append({"turn": 4, "type": "incremental", "kind": r4["kind"], "latency_ms": round((time.perf_counter() - t0) * 1000, 0),
                   "candidates": len(r4.get("viewing", {}).get("candidates", [])) if r4.get("viewing") else 0})

    return {
        "multi_turn": turns,
        "total_latency_ms": sum(t["latency_ms"] for t in turns),
        "clarify_triggered": any(t["kind"] == "clarify" for t in turns),
        "execution_success": any(t["kind"] == "result" for t in turns),
    }


async def test_token_saving():
    """增量执行 vs 全量重跑的 token 对比（通过 prompt 长度估算）。"""
    # 全量重跑：每次都带完整历史
    full_history = [
        ("user", "你好"),
        ("assistant", "你好，我可以帮你找房"),
        ("user", "我想租滨湖的房子"),
        ("assistant", "请问预算多少？"),
        ("user", "3500以内1室"),
        ("assistant", "已找到3套候选"),
    ]
    # 增量执行：带摘要历史
    incremental_history = [
        ("user", "3500以内1室"),
        ("assistant", "（已执行需求：滨湖/3500元/1室，返回3套候选）"),
    ]

    def estimate_tokens(hist):
        total = 0
        for role, content in hist:
            total += len(role) + len(content)
        return total

    full_tokens = estimate_tokens(full_history)
    incr_tokens = estimate_tokens(incremental_history)
    saving = round((1 - incr_tokens / full_tokens) * 100, 1) if full_tokens > 0 else 0

    return {
        "full_history_tokens_est": full_tokens,
        "incremental_history_tokens_est": incr_tokens,
        "token_saving_pct": saving,
    }


async def main():
    print("=" * 60)
    print("RentAI 综合量化测试")
    print("=" * 60)

    # 1. 确定性评测
    print("\n[1/4] 确定性匹配评测...")
    eval_result = run_eval()
    print(json.dumps(eval_result, ensure_ascii=False, indent=2))

    # 2. 管道延迟
    print("\n[2/4] 确定性管道延迟...")
    lat = await test_pipeline_latency()
    print(json.dumps(lat, ensure_ascii=False, indent=2))

    # 3. ReAct 延迟
    print("\n[3/4] ReAct 自主决策延迟（调用百炼，约3次）...")
    react = await test_react_latency()
    print(json.dumps(react, ensure_ascii=False, indent=2))

    # 4. 多轮对话
    print("\n[4/4] 多轮对话测试（调用百炼，约4轮）...")
    dialog = await test_multi_turn_dialogue()
    print(json.dumps(dialog, ensure_ascii=False, indent=2))

    # 5. Token 节省
    print("\n[附加] 增量执行 token 节省估算...")
    token = test_token_saving()
    print(json.dumps(token, ensure_ascii=False, indent=2))

    # 汇总
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    summary = {
        "match_precision@k": eval_result["match_precision@k"],
        "match_recall": eval_result["match_recall"],
        "risk_recall": eval_result["risk_recall"],
        "pipeline_latency_ms_avg": lat["pipeline_latency_ms_avg"],
        "react_latency_ms_avg": react["react_latency_ms_avg"],
        "multi_turn_total_latency_ms": dialog["total_latency_ms"],
        "clarify_triggered": dialog["clarify_triggered"],
        "execution_success": dialog["execution_success"],
        "token_saving_pct": token["token_saving_pct"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
