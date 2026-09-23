# 作者：zcy
"""Reflexion 反思-自纠错回路（能力地图红区缺失项之一）。

模式（参考主流 Reflexion，不抄代码）：执行 → 评估 → 反思 → 重试。
1. **执行**：跑一遍 ReAct `run_react` 产出看房清单。
2. **确定性评估器** `evaluate_viewing`：检查候选数、区域匹配、预算超限、户型匹配——
   用**确定性规则**做质量门（可复现、可评测、零 token）。
3. **LLM 反思** `reflect_once`：仅在评估不通过时触发一次 LLM，分析问题并生成一条可执行改进指令。
4. **重试**：把改进指令并入 `user_note` 重新 `run_react`，最多 `REFLEXION_MAX_ROUNDS` 轮。

关键工程取舍：评估=确定性（不烧 token、可评测），反思=LLM（只在必要时、只产一行指令），上限防死循环。
"""
from __future__ import annotations

from app.core.config import settings
from app.llm.client import get_client
from app.models.schemas import RentRequirement, ViewingList

REFLEXION_MAX_ROUNDS = 2  # 最多反思 2 次（合计最多 3 次执行）


def evaluate_viewing(req: RentRequirement, viewing: ViewingList | None) -> list[str]:
    """确定性质量评估。返回问题列表，空=质量达标。"""
    issues: list[str] = []
    if viewing is None or not viewing.candidates:
        issues.append("未检索到任何候选房源，检索条件可能过严或没有匹配房源。")
        return issues

    cands = viewing.candidates
    d = (req.district or "").strip()
    if d:
        dd = d[:-1] if d.endswith("区") else d
        if not any(c.district and (c.district == dd or c.district == d) for c in cands):
            issues.append(f"候选房源都不在目标区域「{d}」，需调整区域条件。")

    if req.max_price:
        over = [c for c in cands if c.price > req.max_price * 1.05]
        if over and len(over) == len(cands):
            issues.append(f"所有候选都超出预算 {req.max_price}，需下调或放宽预算条件。")

    if req.room_types:
        rts = [r[:-1] if r.endswith("室") else r for r in req.room_types]
        if not any(c.room_type and any(r in (c.room_type or "") for r in rts) for c in cands):
            issues.append(f"候选户型都不匹配需求 {req.room_types}。")

    return issues


async def reflect_once(issues: list[str], req: RentRequirement, round_no: int) -> str:
    """LLM 反思：分析问题根因，产出一条可执行的改进指令（仅一行）。"""
    prompt = (
        "你是 RentAI 的 Agent 反思器。上一轮房源检索结果质量不达标。"
        "请分析根因并给出**一条可执行的改进指令**（20 字以内，只输出指令本身，例如“预算放宽到 6000”或“改搜滨湖区”）。\n"
        f"用户需求：{req.model_dump()}\n"
        f"质量问题（第 {round_no} 轮反思）：\n" + "\n".join(f"- {x}" for x in issues)
    )
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": "你只输出一条改进指令，不解释、不客套。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=100,
    )
    return (resp.choices[0].message.content or "").strip()


async def run_with_reflexion(req: RentRequirement):
    """带反思-自纠错的 Agent 执行。返回 (trace, viewing, reflexion_log)。"""
    from app.agents.react_agent import run_react

    trace, viewing = await run_react(req)
    log: list[dict] = []
    cur_req = req
    for i in range(REFLEXION_MAX_ROUNDS):
        issues = evaluate_viewing(cur_req, viewing)
        if not issues:
            break
        note = await reflect_once(issues, cur_req, i + 1)
        log.append({"round": i + 1, "issues": issues, "improvement": note})
        # 把改进指令并入 user_note，让 ReAct 模型按新指令重试
        merged = (cur_req.user_note or "").strip()
        merged = (merged + "；反思改进：" + note).strip() if merged else "反思改进：" + note
        cur_req = cur_req.model_copy(update={"user_note": merged})
        trace, viewing = await run_react(cur_req)
    return trace, viewing, log
