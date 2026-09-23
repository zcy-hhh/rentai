# 作者：zcy
"""对话式 Agent——把 RentAI 从"表单 CRUD"改成自然语言多轮对话。

设计（参考 Dify 源码的记忆系统重构，不抄代码）：
1. **意图解析**：LLM 每轮从"对话历史 + 用户画像 + 当前消息"推断完整租房需求。
2. **澄清追问**：关键信息不足 → 调用 ask_clarify 追问一个最关键信息，多轮补齐。
3. **多轮累积**：会话内信息不断 merge，直到可执行。
4. **工具编排**：需求齐全 → 调用 submit_requirement → 复用 ReAct 走完整检索/过滤/排序/避坑/清单。
5. **三层记忆（参考 Dify conversations/messages/user_profiles 表）**：
   - 工作记忆：进程内存 / LangGraph State，单次请求内有效
   - 短期记忆：PG conversations + messages 表，session_id 隔离，无 TTL 永久保存，
     token 反向累计修剪（参考 Dify 从最新消息往前累加 token 超限截断）
   - 长期记忆：PG user_profiles 表，user_id 隔离，无 TTL，upsert 更新偏好
   Redis 只做热缓存，PG 是真相源——解决旧版"TTL 1天/7天明天东西就没了"的问题。
"""
from __future__ import annotations

import json
import re
import time

from app.llm.client import get_client, is_configured
from app.llm import client as llm
from app.core.config import settings
from app.agents.react_agent import run_react
from app.agents.reflexion import run_with_reflexion, evaluate_viewing
from app.agents.graph import rent_graph
from app.models.schemas import RentRequirement
from app.observability import build_usage, record_usage
from app.memory import (
    append_message,
    get_history,
    get_or_create_conversation,
    get_profile,
    profile_text,
    save_agent_thought,
    trim_history,
    update_profile,
)

_INTENT_SYSTEM = (
    "你是智能租房助手 RentAI 的意图理解模块。根据用户的自然语言消息（结合历史对话与用户画像），决定下一步：\n"
    "- 若信息足以构成一条可执行的租房需求 → 调用 `submit_requirement`，填入你能确定的所有字段；不确定的字段省略，绝不编造用户没说的约束。\n"
    "- 若连「预算」和「区域」这些关键检索条件都缺失 → 调用 `ask_clarify`，追问**最关键的 1 个**信息（如预算、区域），一次只问一个。\n"
    "- 若用户在闲聊/问功能 → 直接自然语言回复，不调用工具。\n"
    "模式选择（submit_requirement 的 mode 字段）：需求简单明确（有清晰区域/预算/户型，如'滨湖3000以内1室'）→ mode='workflow'，走确定性管道快速稳定返回；需求复杂/模糊/需要多工具灵活组合（如'帮我找性价比高的、通勤方便的'）→ mode='react'，走自主决策。默认 react。\n"
    "宁可先 ask_clarify 补全，也不要编造需求。所有结论严格来自用户消息与已知画像。\n"
    "增量原则：若历史中已有执行结果，用户新增/修改条件时应**在该基础上增量执行**（结合上次需求调整），"
    "不要重复生成与上次完全相同的旧需求；确属全新需求才正常执行。"
)

_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_requirement",
            "description": "需求信息已足够，提交一条可执行的租房需求",
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {"type": "string", "description": "意向区域，如 滨湖/梁溪/新吴/锡山/惠山，未知省略"},
                    "max_price": {"type": "number", "description": "月租预算上限（元），如 5000"},
                    "min_area": {"type": "number", "description": "最小面积（㎡）"},
                    "room_types": {"type": "array", "items": {"type": "string"}, "description": "可接受户型，如 ['1室','2室']"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "偏好标签，如 ['近地铁','精装']"},
                    "commute_to": {"type": "string", "description": "通勤目的地"},
                    "commute_max_minutes": {"type": "number", "description": "通勤时间上限（分钟）"},
                    "user_note": {"type": "string", "description": "用户补充的自由指令（如 只要最便宜的3套、不用查风险）"},
                    "mode": {"type": "string", "enum": ["workflow", "react"], "description": "执行模式：workflow=确定性管道（快速稳定，适合明确需求）；react=自主决策（适合复杂/模糊需求）。默认 react"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarify",
            "description": "关键检索信息不足，向用户追问最需要的一个信息",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "一次只问一个最关键的澄清问题"}},
                "required": ["question"],
            },
        },
    },
]


def _update_profile_from_req(p: dict, req: RentRequirement) -> dict:
    """把一次已执行的需求并入用户画像（长期记忆）。返回需要 update 的 patch。"""
    patch = {}
    if req.district:
        patch["districts"] = [req.district]
    if req.max_price:
        lo = (int(req.max_price) // 1000) * 1000
        patch["budgets"] = [(lo - 1000, lo)]
    if req.room_types:
        patch["room_types"] = list(req.room_types)
    if req.tags:
        patch["tags"] = list(req.tags)
    return patch


def _build_requirement(args: dict) -> RentRequirement:
    return RentRequirement(
        district=args.get("district"),
        max_price=float(args["max_price"]) if args.get("max_price") else 5000.0,
        min_area=float(args["min_area"]) if args.get("min_area") else None,
        room_types=args.get("room_types") or ["1室", "2室", "3室"],
        tags=args.get("tags") or [],
        commute_to=args.get("commute_to"),
        commute_max_minutes=int(args["commute_max_minutes"]) if args.get("commute_max_minutes") else None,
        user_note=args.get("user_note"),
    )


def _parse_args(raw: str | None) -> dict:
    """宽松解析大模型返回的工具参数（百炼 qwen 偶发宽松 JSON：中文引号/缺逗号）。"""
    raw = (raw or "").strip()
    if not raw:
        return {}
    for attempt in (raw,):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            pass
    fixed = raw.replace(""", '"').replace(""", '"').replace("'", "'").replace("'", "'")
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    for cand in (fixed,):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    idx = fixed.find("{")
    end = fixed.rfind("}")
    if idx != -1 and end > idx:
        try:
            return json.loads(fixed[idx : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _to_dict_list(obj):
    """pydantic 模型 → dict（供 JSON 返回）。"""
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


def _result_summary(req: RentRequirement, viewing, escalated: bool = False) -> str:
    """把一次执行结果浓缩成一句，存入会话 history——让后续轮次的模型能"看到上次生成了什么"，
    从而新增需求时做增量而非重复生成。"""
    d = req.district or "区域不限"
    rt = "/".join(req.room_types or [])
    base = f"{d} / {req.max_price}元 / {rt}"
    if escalated:
        return f"（上一轮需求 {base} 未匹配到房源，已转人工。如需继续请放宽区域/预算/户型后重说。）"
    if not viewing or not viewing.candidates:
        return f"（上一轮需求 {base} 返回 0 套候选，可放宽条件重试。）"
    first = viewing.candidates[0]
    return (
        f"（已执行需求 {base}：返回 {len(viewing.candidates)} 套候选，"
        f"首套 {first.title}·{first.district} ¥{first.price}。"
        f"如需在此基础上新增/修改条件请直接说。）"
    )


async def chat_step(uid: str, session_id: str, user_msg: str, history: list | None = None) -> dict:
    """对话式 Agent 单轮推进。返回给前端的一步结果。

    记忆重构（参考 Dify）：
    - 短期记忆从 PG messages 表读（带 token 反向累计修剪），前端 history 作为真相源兜底
    - 长期记忆从 PG user_profiles 表读，无 TTL
    - 每轮结束后消息持久化到 PG messages 表
    """
    if not is_configured():
        return {"kind": "message", "text": "未配置 DASHSCOPE_API_KEY，无法进行对话式检索。"}

    # 确保会话存在（PG 持久化，无 TTL）
    await get_or_create_conversation(session_id, uid)

    # 短期记忆：优先用前端携带的 history（真相源），否则从 PG 读并做 token 修剪
    if history is not None:
        ctx_hist = [{"role": r, "content": c} for r, c in history]
        ctx_hist = trim_history(ctx_hist)
    else:
        ctx_hist = await get_history(session_id)

    # 长期记忆：从 PG user_profiles 读（无 TTL，永久保存）
    prof = await get_profile(uid)

    messages = [
        {"role": "system", "content": _INTENT_SYSTEM + "\n用户画像：" + profile_text(prof)},
        *ctx_hist,
        {"role": "user", "content": user_msg},
    ]

    client = get_client()
    _t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        tools=_INTENT_TOOLS,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=800,
    )
    latency_ms = int((time.perf_counter() - _t0) * 1000)
    _u = resp.usage
    _pt = int(getattr(_u, "prompt_tokens", 0) or 0)
    _ct = int(getattr(_u, "completion_tokens", 0) or 0)
    choice = resp.choices[0].message

    # 1) 模型直接回复（闲聊/说明）—— 持久化到 PG messages 表
    if not choice.tool_calls and choice.content:
        await append_message(session_id, "user", user_msg, latency_ms=0)
        await append_message(session_id, "assistant", choice.content, tokens=_ct, latency_ms=latency_ms)
        record_usage(build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=0, extra_llm_calls=0))
        return {"kind": "message", "text": choice.content, "session_id": session_id}

    # 2) 澄清追问 —— 持久化到 PG messages 表
    if choice.tool_calls and choice.tool_calls[0].function.name == "ask_clarify":
        args = _parse_args(choice.tool_calls[0].function.arguments)
        q = args.get("question") or "请补充预算或区域等信息，我好帮你找房。"
        await append_message(session_id, "user", user_msg, latency_ms=0)
        await append_message(session_id, "assistant", q, tokens=_ct, latency_ms=latency_ms)
        record_usage(build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=0, extra_llm_calls=0))
        return {"kind": "clarify", "text": q, "session_id": session_id}

    # 3) 提交需求并执行——AI 自主选择模式：workflow（确定性管道）或 react（自主决策+反思）
    if choice.tool_calls and choice.tool_calls[0].function.name == "submit_requirement":
        args = _parse_args(choice.tool_calls[0].function.arguments)
        req = _build_requirement(args)
        mode = args.get("mode", "react")
        if mode == "workflow":
            state = await rent_graph.ainvoke({"requirement": req})
            viewing = state.get("viewing_list")
            trace = [{"tool": t, "thought": ""} for t in ["retrieve", "filter", "rank", "risk_check", "build_list"]]
            reflexion = []
        else:
            trace, viewing, reflexion = await run_with_reflexion(req)

        # 长期记忆：把本次需求并入 PG user_profiles（upsert，无 TTL）
        patch = _update_profile_from_req({}, req)
        await update_profile(uid, patch)

        issues = evaluate_viewing(req, viewing)
        escalated = bool(reflexion and issues)

        # 短期记忆：把"执行摘要"存入 PG messages 表（后续轮次可见上次结果，做增量）
        summary = _result_summary(req, viewing, escalated=escalated)
        await append_message(session_id, "user", user_msg, latency_ms=0)
        assistant_msg = await append_message(session_id, "assistant", summary, tokens=_ct, latency_ms=latency_ms)

        # Agent 思考过程持久化（参考 Dify message_agent_thoughts 表）：每步 thought/tool/tool_input 存库
        for pos, step in enumerate(trace):
            await save_agent_thought(
                message_id=assistant_msg.id,
                position=pos,
                thought=step.get("thought", ""),
                tool=step.get("tool", ""),
                tool_input=step.get("args", step.get("tool_input", {})),
                observation=step.get("observation", ""),
            )

        usage = build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=len(reflexion), extra_llm_calls=1)
        record_usage(usage)
        if escalated:
            return {
                "kind": "escalate",
                "session_id": session_id,
                "requirement": req.model_dump(),
                "trace": trace,
                "reflexion": reflexion,
                "escalation": {
                    "reason": issues,
                    "context": f"需求 {req.model_dump()}，Agent 反思 {len(reflexion)} 轮仍未满足。",
                    "advice": "可联系人工租房顾问，或放宽区域/预算/户型条件后重试。",
                },
                "usage": usage,
            }
        return {
            "kind": "result",
            "session_id": session_id,
            "requirement": req.model_dump(),
            "trace": trace,
            "reflexion": reflexion,
            "viewing": _to_dict_list(viewing) if viewing else None,
            "usage": usage,
        }

    # 兜底
    return {"kind": "message", "text": choice.content or "抱歉，我没能理解，请重新描述需求。"}


async def reset_session(session_id: str):
    """软删除会话（参考 Dify is_deleted，不物理删除）。"""
    from app.memory import delete_conversation
    await delete_conversation(session_id)


async def record_user_preference(uid: str, req: RentRequirement):
    """用户确认/调整看房清单后，把需求并入长期画像（PG user_profiles，无 TTL）。

    作用：让"确认/调整"有实际业务含义——用户明确认可或调整过的需求，
    会被 Agent 记住并用于后续推荐，而不是确认后清单就废弃。
    """
    patch = _update_profile_from_req({}, req)
    await update_profile(uid, patch)
