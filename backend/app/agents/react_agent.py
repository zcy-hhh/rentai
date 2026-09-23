# 作者：zcy
"""ReAct Agent 内核（M9）——模型自主决策的真 Agent。

用 LangGraph 标准 `create_react_agent`：LLM 作为推理引擎，通过 function calling
自主决定调用哪些工具、顺序与步数；工具操作共享 AgentCtx，返回摘要给模型观察，
直到模型收敛（调用 build_viewing_list 产出清单）。

与确定性管道（agents/graph.py）的关系：React 是本项目的 Agent 主路径；确定性
管道保留为兜底/基准（可评测对照）。两者共用同一套确定性执行函数，保证结果可复现。
"""
from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.agents.react_tools import reset_ctx, tools
from app.llm.agent_llm import build_agent_llm
from app.models.schemas import RentRequirement, ViewingList

SYSTEM_PROMPT = """你是智能租房助手 RentAI。用户给出租房需求后，你自主调用工具完成从检索到看房清单的全流程。

工具（search_listings 必须最先；build_viewing_list 必须最后调用并以它收尾）：
- search_listings：检索候选房源（必须最先调用）
- filter_hard：硬条件过滤（价格/面积/户型）
- score_rank：评分排序（默认应执行；仅当用户明确说"不用排序"时才跳过）
- check_risks：避坑检查（默认应执行；仅当用户明确说"不用查风险"时才跳过）
- build_viewing_list：生成最终看房清单（必须最后调用收尾；即便跳过排序也能生成）
- amap_geocode：地理编码，把地址解析成真实经纬度（需要精确位置/后续周边/通勤时调用）
- amap_poi_around：周边配套检索（地铁/超市/学校/医院，含距离；用户问"周边"/"配套"/"近地铁"等时调用）
- amap_commute：公交通勤时长估算（用户要求按通勤时间筛选/比较时调用）

默认走完整流程：search → filter → score_rank → check_risks → build。只有当用户**明确**要求跳过某步时才跳过对应工具，其余步骤照常执行。高德工具为增强项，仅当需求涉及真实位置、周边配套或通勤时自主调用。你自主决定排序方式（sort_by）与清单数量（top_k）等参数。工具会返回候选摘要供你观察。不要编造房源数据，一切以工具返回为准。"""


def _describe(req: RentRequirement) -> str:
    parts = [
        f"区域：{req.district}" if req.district else "区域不限",
        f"月租预算：{int(req.max_price)}元以内",
        f"户型：{'、'.join(req.room_types)}",
    ]
    if req.min_area:
        parts.append(f"最小面积：{int(req.min_area)}㎡")
    if req.commute_to:
        parts.append(f"通勤目的地：{req.commute_to}" + (f"，上限{req.commute_max_minutes}分钟" if req.commute_max_minutes else ""))
    if req.tags:
        parts.append(f"偏好：{'、'.join(req.tags)}")
    if req.user_note:
        parts.append(f"用户补充要求（请据此自主决定如何调用工具，可跳过或重复某些步骤）：{req.user_note}")
    return "\n".join(parts)


def build_react_agent():
    return create_agent(
        model=build_agent_llm(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )


async def run_react(req: RentRequirement) -> tuple[list[dict], ViewingList | None]:
    """执行 ReAct Agent，返回工具调用轨迹 + 最终清单。

    trace: 模型每次调用工具的记录（tool 名 + 参数 + 结果摘要），供前端/观测展示。
    """
    reset_ctx(req)
    agent = build_react_agent()
    inputs = {"messages": [HumanMessage(content=_describe(req))]}
    trace: list[dict] = []
    async for event in agent.astream(inputs):
        for _, payload in event.items():
            msgs = payload.get("messages") if isinstance(payload, dict) else None
            if not msgs:
                continue
            for msg in msgs:
                # 完整 AIMessage 的工具调用
                tcs = getattr(msg, "tool_calls", None) or []
                if tcs:
                    for tc in tcs:
                        trace.append({
                            "tool": tc.get("name", ""),
                            "args": tc.get("args", {}),
                            "thought": getattr(msg, "content", "") or "",
                        })
                    continue
                # AIMessageChunk 的工具调用（astream 下常见，取 name）
                for c in getattr(msg, "tool_call_chunks", None) or []:
                    name = c.get("name") or ""
                    if name:
                        trace.append({
                            "tool": name,
                            "args": {},
                            "thought": getattr(msg, "content", "") or "",
                        })
    # 取最终清单（在共享 ctx）
    from app.agents.react_tools import _ctx

    return trace, _ctx.viewing_list
