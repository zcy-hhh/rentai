# 作者：zcy
"""对话式 Agent（M12 重构核心）——把 RentAI 从"表单 CRUD"改成自然语言多轮对话。

设计（参考主流 Agent 的意图解析 + 澄清 + 记忆，不抄代码）：
1. **意图解析**：LLM 每轮从"对话历史 + 用户画像 + 当前消息"推断完整租房需求。
2. **澄清追问**：关键信息不足（连预算/区域都没有）→ 调用 `ask_clarify` 追问一个最关键信息，多轮补齐。
3. **多轮累积**：会话内信息不断 merge，直到可执行。
4. **工具编排**：需求齐全 → 调用 `submit_requirement` → 复用 M9 的 ReAct `run_react` 走完整检索/过滤/排序/避坑/清单。
5. **记忆（持久化）**：短期=会话历史（session_id），长期=用户画像（user_id）；两者都存 **Redis**（带 TTL），
   Redis 不可用时自动降级进程内存（保证无 Redis 环境可测）。生产可进一步把画像向量化入 pgvector。
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

# ---- 记忆持久化：短期会话 / 长期画像。Redis 优先，Redis 不可用自动降级进程内存 ----
SESSION_TTL = 86_400   # 会话 1 天
PROFILE_TTL = 604_800  # 画像 7 天
_MEM: dict[str, str] = {}  # 降级用（Redis 不可用时）
_redis = None
_redis_fail = False


def _redis_conn():
    """惰性创建 asyncio Redis 连接；失败一次后标记降级，避免每轮重连。"""
    global _redis, _redis_fail
    if _redis_fail:
        return None
    try:
        from redis import asyncio as aioredis

        if _redis is None:
            _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return _redis
    except Exception:
        _redis_fail = True
        return None


async def _get(key: str) -> dict:
    r = _redis_conn()
    if r:
        try:
            raw = await r.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    if key in _MEM:
        return json.loads(_MEM[key])
    return {}


async def _set(key: str, val: dict, ttl: int | None = None):
    r = _redis_conn()
    if r:
        try:
            await r.set(key, json.dumps(val, ensure_ascii=False), ex=ttl)
            return
        except Exception:
            pass
    _MEM[key] = json.dumps(val, ensure_ascii=False)


async def _delete(key: str):
    r = _redis_conn()
    if r:
        try:
            await r.delete(key)
            return
        except Exception:
            pass
    _MEM.pop(key, None)


_INTENT_SYSTEM = (
    "你是智能租房助手 RentAI 的意图理解模块。根据用户的自然语言消息（结合历史对话与用户画像），决定下一步：\n"
    "- 若信息足以构成一条可执行的租房需求 → 调用 `submit_requirement`，填入你能确定的所有字段；不确定的字段省略，绝不编造用户没说的约束。\n"
    "- 若连“预算”和“区域”这些关键检索条件都缺失 → 调用 `ask_clarify`，追问**最关键的 1 个**信息（如预算、区域），一次只问一个。\n"
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


def _profile_text(p: dict) -> str:
    """把用户画像 dict 渲染成注入意图 System Prompt 的一段文字。"""
    if not p:
        return "（新用户，暂无画像）"
    parts = []
    if p.get("districts"):
        parts.append("常用区域：" + "、".join(p["districts"]))
    if p.get("budgets"):
        parts.append("常用预算区间：" + "、".join(f"{a}-{b}元" for a, b in p["budgets"][-3:]))
    if p.get("room_types"):
        parts.append("常用户型：" + "、".join(p["room_types"]))
    if p.get("tags"):
        parts.append("偏好：" + "、".join(p["tags"]))
    return "；".join(parts) if parts else "（画像正在积累）"


def _update_profile(p: dict, req: RentRequirement):
    """把一次已执行的需求并入用户画像（长期记忆）。"""
    p.setdefault("districts", [])
    p.setdefault("budgets", [])
    p.setdefault("room_types", [])
    p.setdefault("tags", [])
    if req.district and req.district not in p["districts"]:
        p["districts"].append(req.district)
    if req.max_price:
        # 简化：按 1000 档位粗存
        lo = (int(req.max_price) // 1000) * 1000
        pair = (lo - 1000, lo)
        p["budgets"].append(pair)
    for rt in req.room_types:
        if rt and rt not in p["room_types"]:
            p["room_types"].append(rt)
    for t in req.tags:
        if t and t not in p["tags"]:
            p["tags"].append(t)


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
    # 宽松修复：中文引号转英文、去多余尾逗号、截取到第一个完整对象
    fixed = raw.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
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

    history：前端携带的完整对话历史 [(role, content), ...]，作为上下文**真相源**——
    即使 Redis 会话记忆过期/降级丢失，后端也能基于前端历史继续多轮（避免"新增需求重复生成"）。
    缺省时回退 Redis 会话记忆。
    """
    if not is_configured():
        return {"kind": "message", "text": "未配置 DASHSCOPE_API_KEY，无法进行对话式检索。"}

    skey = f"rentai:session:{session_id}"
    pkey = f"rentai:profile:{uid}"
    sess = await _get(skey)
    sess.setdefault("history", [])
    prof = await _get(pkey)

    # 上下文真相源：前端历史优先（覆盖 Redis 过期/降级缺失），并同步写回 Redis 供跨设备兜底
    ctx_hist = history if history is not None else sess["history"]
    if history is not None:
        sess["history"] = list(ctx_hist)

    messages = [
        {"role": "system", "content": _INTENT_SYSTEM + "\n用户画像：" + _profile_text(prof)},
        *[{"role": r, "content": c} for r, c in ctx_hist],
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
    latency_ms = int((time.perf_counter() - _t0) * 1000)  # 可观测性：端到端延迟
    _u = resp.usage
    _pt = int(getattr(_u, "prompt_tokens", 0) or 0)
    _ct = int(getattr(_u, "completion_tokens", 0) or 0)
    choice = resp.choices[0].message

    # 1) 模型直接回复（闲聊/说明）
    if not choice.tool_calls and choice.content:
        sess["history"].append(("user", user_msg))
        sess["history"].append(("assistant", choice.content))
        await _set(skey, sess, ttl=SESSION_TTL)
        record_usage(build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=0, extra_llm_calls=0))
        return {"kind": "message", "text": choice.content, "session_id": session_id}

    # 2) 澄清追问
    if choice.tool_calls and choice.tool_calls[0].function.name == "ask_clarify":
        args = _parse_args(choice.tool_calls[0].function.arguments)
        q = args.get("question") or "请补充预算或区域等信息，我好帮你找房。"
        sess["history"].append(("user", user_msg))
        sess["history"].append(("assistant", q))
        await _set(skey, sess, ttl=SESSION_TTL)
        record_usage(build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=0, extra_llm_calls=0))
        return {"kind": "clarify", "text": q, "session_id": session_id}

    # 3) 提交需求并执行——AI 自主选择模式：workflow（确定性管道）或 react（自主决策+反思）
    if choice.tool_calls and choice.tool_calls[0].function.name == "submit_requirement":
        args = _parse_args(choice.tool_calls[0].function.arguments)
        req = _build_requirement(args)
        mode = args.get("mode", "react")
        if mode == "workflow":
            # 确定性管道：LangGraph 固定五节点，快速稳定，适合需求明确的场景
            state = await rent_graph.ainvoke({"requirement": req})
            viewing = state.get("viewing_list")
            trace = [{"tool": t, "thought": ""} for t in ["retrieve", "filter", "rank", "risk_check", "build_list"]]
            reflexion = []
        else:
            # 自主决策：ReAct + 反思自纠错，适合复杂/模糊需求
            trace, viewing, reflexion = await run_with_reflexion(req)
        _update_profile(prof, req)  # 把本次需求并入长期画像
        issues = evaluate_viewing(req, viewing)
        escalated = bool(reflexion and issues)
        # 把"执行摘要"而非占位文本存进 history，后续轮次模型可见上次结果，做增量而非重复
        sess["history"].append(("user", user_msg))
        sess["history"].append(("assistant", _result_summary(req, viewing, escalated=escalated)))
        await _set(pkey, prof, ttl=PROFILE_TTL)
        await _set(skey, sess, ttl=SESSION_TTL)
        usage = build_usage(prompt_tokens=_pt, completion_tokens=_ct, latency_ms=latency_ms, retry_rounds=len(reflexion), extra_llm_calls=1)
        record_usage(usage)  # 累计进观测指标（供观测后台快照）
        if escalated:  # 人工兜底升级（能力地图红区缺失项）：反思多次仍未达标 → 升级人工坐席
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
            "reflexion": reflexion,  # 反思日志（若评估不通过则为非空列表）
            "viewing": _to_dict_list(viewing) if viewing else None,
            "usage": usage,
        }

    # 兜底
    return {"kind": "message", "text": choice.content or "抱歉，我没能理解，请重新描述需求。"}


async def reset_session(session_id: str):
    """清除某个会话的记忆（Redis + 内存降级）。"""
    await _delete(f"rentai:session:{session_id}")


async def record_user_preference(uid: str, req: RentRequirement):
    """用户确认/调整看房清单后，把需求并入长期画像（后续 Agent 找房会参考）。

    作用：让"确认/调整"有实际业务含义——用户明确认可或调整过的需求，
    会被 Agent 记住并用于后续推荐，而不是确认后清单就废弃。
    """
    pkey = f"rentai:profile:{uid}"
    prof = await _get(pkey)
    _update_profile(prof, req)
    await _set(pkey, prof, ttl=PROFILE_TTL)
