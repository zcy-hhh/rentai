# 作者：zcy
"""LangGraph 图定义：多 Agent 编排入口。

节点顺序：retrieve → filter → rank → risk_check → build_list → END。
build_list 产物进入 HITL（服务层管理确认状态）。
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    node_build_list,
    node_filter,
    node_rank,
    node_retrieve,
    node_risk_check,
)
from app.models.schemas import CandidateListing, Listing, RentRequirement, ViewingList


class RentState(TypedDict, total=False):
    requirement: RentRequirement
    raw: list[Listing]
    filtered: list[Listing]
    ranked: list[CandidateListing]
    viewing_list: ViewingList


def build_graph():
    graph = StateGraph(RentState)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("filter", node_filter)
    graph.add_node("rank", node_rank)
    graph.add_node("risk_check", node_risk_check)
    graph.add_node("build_list", node_build_list)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "filter")
    graph.add_edge("filter", "rank")
    graph.add_edge("rank", "risk_check")
    graph.add_edge("risk_check", "build_list")
    graph.add_edge("build_list", END)

    return graph.compile()


rent_graph = build_graph()
