# 作者：zcy
"""多 Agent 协作：Planner-Executor-Verifier（能力地图红区缺失项之一）。

角色分工（参考主流多 Agent 编排，不抄代码）：
1. **Planner**：LLM 把用户需求分解成 3-5 个可执行步骤（显式任务分解，体现"规划/推理"）。
2. **Executor**：执行检索编排——复用 M9 ReAct `run_react`（模型自主调工具产出看房清单）。
3. **Verifier**：LLM 校验执行结果是否达成 Planner 计划与用户需求，给出"已达成/缺失X"结论。

三者各司其职：Planner 决定"做什么"，Executor 决定"怎么做"，Verifier 决定"做没做对"。
LLM 调用可注入（默认百炼），测试可传 fake 不烧 token。
"""
from __future__ import annotations

import json

from app.core.config import settings
from app.models.schemas import RentRequirement

_PLAN_SYSTEM = (
    "你是 RentAI 的 Planner。把用户的租房需求分解为 3-5 个可执行的检索步骤。"
    "只输出 JSON 数组，每个元素是 {\"step\": 序号, \"action\": \"一句话动作\"}，不要其他文字。"
)
_VERIFY_SYSTEM = (
    "你是 RentAI 的 Verifier。对照 Planner 的计划与用户需求，检查 Executor 产出的看房清单是否达成目标。"
    "只输出结论：若全部达成输出「已达成」；若有缺口，输出「缺失：具体缺口」。不要客套。"
)


def _parse_steps(text: str) -> list[dict]:
    """宽松解析 Planner 返回的 JSON 步骤数组。"""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # 截取最外层 [ ... ] 再解析
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return []


def _default_chat():
    from app.llm.client import get_client

    return get_client()


async def _llm_text(chat, messages: list[dict], max_tokens: int) -> str:
    if callable(chat):  # 测试注入的 fake
        return await chat(messages)
    resp = await chat.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


async def _plan(chat, req: RentRequirement) -> list[dict]:
    text = await _llm_text(
        chat,
        [
            {"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user", "content": f"需求：{req.model_dump()}\n请输出执行计划 JSON。"},
        ],
        max_tokens=400,
    )
    return _parse_steps(text)


async def _verify(chat, req: RentRequirement, steps: list[dict], viewing) -> dict:
    summary = "无候选"
    if viewing and getattr(viewing, "candidates", None):
        cs = viewing.candidates
        summary = f"{len(cs)} 套候选，示例：{cs[0].title} {cs[0].district} {cs[0].price}元；"
    plan_text = "；".join(f"{s.get('step')}.{s.get('action')}" for s in steps) or "（无计划）"
    text = await _llm_text(
        chat,
        [
            {"role": "system", "content": _VERIFY_SYSTEM},
            {"role": "user", "content": f"需求：{req.model_dump()}\n计划：{plan_text}\n执行结果：{summary}"},
        ],
        max_tokens=120,
    )
    achieved = "已达成" in text and "缺失" not in text
    return {"verdict": text, "achieved": achieved}


async def planner_executor_verifier(req: RentRequirement, chat=None, execute=None):
    """Planner-Executor-Verifier 编排。返回 {steps, trace, viewing, verify}。

    chat / execute 均可注入（默认百炼 + ReAct run_react），测试传 fake 不烧 token。
    """
    chat = chat or _default_chat()
    if execute is None:
        from app.agents.react_agent import run_react

        execute = run_react

    steps = await _plan(chat, req)             # Planner：显式任务分解
    trace, viewing = await execute(req)        # Executor：执行检索编排
    verify = await _verify(chat, req, steps, viewing)  # Verifier：校验结论
    return {"steps": steps, "trace": trace, "viewing": viewing, "verify": verify}
