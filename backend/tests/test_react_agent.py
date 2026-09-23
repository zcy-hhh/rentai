# 作者：zcy
"""ReAct Agent 测试：用 fake 模型验证"模型自主调用工具"的循环与收敛。

不访问真实 LLM（不烧钱）——fake 模型按预定序列返回 tool_call，
验证 create_react_agent 的 ReAct 循环正确执行每个工具并最终产出清单。
"""
from __future__ import annotations

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.db.mock_listings import MOCK_LISTINGS
from app.models.schemas import Listing, RentRequirement


class FakeReactModel(BaseChatModel):
    """按调用次数返回预定义 tool_call 序列的假模型。"""

    @property
    def _llm_type(self) -> str:
        return "fake-react"

    def bind_tools(self, tools, **kwargs):
        # fake 直接按序列返回 tool_call，不需要真正绑定工具
        return self

    def __init__(self, steps: list[dict]) -> None:
        super().__init__()
        self._steps = steps
        self._i = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self._i >= len(self._steps):
            msg = AIMessage(content="完成")
        else:
            step = self._steps[self._i]
            self._i += 1
            tcs = step.get("tool_calls", [])
            if tcs:
                msg = AIMessage(
                    content=step.get("thought", ""),
                    tool_calls=[
                        {"name": name, "args": {}, "id": f"call_{self._i}_{j}", "type": "tool_call"}
                        for j, name in enumerate(tcs)
                    ],
                )
            else:
                msg = AIMessage(content=step.get("content", "完成"))
        return ChatResult(generations=[ChatGeneration(message=msg)])


STEPS = [
    {"thought": "先检索候选房源", "tool_calls": ["search_listings"]},
    {"tool_calls": ["filter_hard"]},
    {"tool_calls": ["score_rank"]},
    {"tool_calls": ["check_risks"]},
    {"tool_calls": ["build_viewing_list"]},
    {"content": "清单已生成"},
]


async def _fake_hybrid(req: RentRequirement) -> list[Listing]:
    """测试用确定性检索：返回前 5 套 mock，不访问真实 LLM。"""
    return [Listing(**r) for r in MOCK_LISTINGS[:5]]


@pytest.mark.asyncio
async def test_react_agent_autonomous_tool_calls(monkeypatch):
    """模型自主按序调用 5 个工具并收敛产出清单。"""
    monkeypatch.setattr("app.agents.react_tools.hybrid_search", _fake_hybrid)
    monkeypatch.setattr(
        "app.agents.react_agent.build_agent_llm",
        lambda: FakeReactModel([dict(s) for s in STEPS]),
    )

    from app.agents.react_agent import run_react

    req = RentRequirement(
        district="新吴区",
        max_price=3000,
        min_area=20,
        room_types=["1室", "2室"],
        tags=["近地铁"],
    )
    trace, vl = await run_react(req)

    # 模型自主调用轨迹：5 个工具按序出现
    tools_called = [t["tool"] for t in trace]
    assert tools_called == [
        "search_listings",
        "filter_hard",
        "score_rank",
        "check_risks",
        "build_viewing_list",
    ]
    # 收敛产出清单
    assert vl is not None
    assert vl.status == "pending"
    assert len(vl.candidates) > 0
    assert vl.candidates[0].match_score >= 0


@pytest.mark.asyncio
async def test_react_agent_ctx_reset_between_runs(monkeypatch):
    """两次运行共享 ctx 需重置，不串数据。"""
    monkeypatch.setattr("app.agents.react_tools.hybrid_search", _fake_hybrid)
    monkeypatch.setattr(
        "app.agents.react_agent.build_agent_llm",
        lambda: FakeReactModel([dict(s) for s in STEPS]),
    )

    from app.agents.react_agent import run_react

    req1 = RentRequirement(district="新吴区", max_price=3000, room_types=["1室"])
    req2 = RentRequirement(district="滨湖区", max_price=5000, room_types=["2室"])
    _, vl1 = await run_react(req1)
    _, vl2 = await run_react(req2)
    assert vl1 is not None and vl2 is not None
    assert vl1.requirement.district == "新吴区"
    assert vl2.requirement.district == "滨湖区"
