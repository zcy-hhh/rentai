# 作者：zcy
"""Harness 治理：Agent 可靠性护栏（M6）。

对应"Agent 内核（harness）"的可靠性职责，两块：
1. **死循环检测**：LangGraph `recursion_limit` 守卫 + `GraphRecursionError` 转换，超限报错不挂死。
2. **上下文护栏**：输入越界校验（字段长度/数量/数值范围）+ 候选数量上限，防超长输入、防上下文膨胀、防注入。

统一入口 `safe_stream` / `guard_requirement` 供 API 层调用，护栏失败抛明确的 `HarnessError`。
"""
from __future__ import annotations

from langgraph.errors import GraphRecursionError

from app.agents.graph import rent_graph
from app.models.schemas import RentRequirement

# ---- 护栏阈值（可配置） ----
MAX_STEPS = 20  # 死循环守卫：单次编排最大步骤数
MAX_DISTRICT_LEN = 50  # 意向区域字段长度上限
MAX_ROOM_TYPES = 6  # 可接受户型数量上限
MAX_TAGS = 10  # 偏好标签数量上限
MAX_PRICE = 100_000  # 月租金上限（元）
MAX_CANDIDATES = 30  # 候选上限（防响应膨胀）


class HarnessError(Exception):
    """Harness 治理统一异常基类。"""


class AgentStepLimitError(HarnessError):
    """死循环检测：执行步骤超过上限。"""

    def __init__(self, steps: int) -> None:
        super().__init__(f"Agent 执行超过步骤上限 {steps}，疑似死循环，已终止")


class ContextGuardError(HarnessError):
    """上下文护栏：输入越界。"""


def guard_requirement(req: RentRequirement) -> None:
    """上下文护栏：校验输入边界，非法输入抛 ContextGuardError。

    防超长文本、防异常数量、防荒谬数值（间接防注入与上下文膨胀）。
    """
    if (req.district or "") and len(req.district) > MAX_DISTRICT_LEN:
        raise ContextGuardError(f"意向区域超长（>{MAX_DISTRICT_LEN} 字符）")
    if len(req.room_types) > MAX_ROOM_TYPES:
        raise ContextGuardError(f"可接受户型数量超限（>{MAX_ROOM_TYPES} 个）")
    if len(req.tags) > MAX_TAGS:
        raise ContextGuardError(f"偏好标签数量超限（>{MAX_TAGS} 个）")
    if not (0 < req.max_price <= MAX_PRICE):
        raise ContextGuardError(f"月租金需在 (0, {MAX_PRICE}] 区间")
    if req.min_area is not None and not (0 < req.min_area <= 10_000):
        raise ContextGuardError("最小面积需在 (0, 10000] ㎡ 区间")


def _truncate(event: dict) -> dict:
    """护栏：候选超限截断，防响应/上下文膨胀。"""
    for key in ("raw", "filtered", "ranked"):
        if key in event and isinstance(event[key], list) and len(event[key]) > MAX_CANDIDATES:
            event[key] = event[key][:MAX_CANDIDATES]
    return event


async def safe_stream(req: RentRequirement):
    """带护栏的流式编排。

    yield 形如 `{"node_name": 节点增量}` 的事件序列；死循环超限抛
    `AgentStepLimitError`（而非让 LangGraph 内部错误/挂死）。
    """
    guard_requirement(req)
    try:
        async for event in rent_graph.astream(
            {"requirement": req},
            stream_mode="updates",
            config={"recursion_limit": MAX_STEPS},
        ):
            yield _truncate(event)
    except GraphRecursionError as e:  # 死循环护栏：超 recursion_limit 被 LangGraph 触发
        raise AgentStepLimitError(MAX_STEPS) from e
