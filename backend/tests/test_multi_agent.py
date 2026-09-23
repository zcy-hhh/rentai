# -*- coding: utf-8 -*-
# 作者：zcy
"""多 Agent 协作（Planner-Executor-Verifier）单测——注入 fake，不烧真实 token。"""
import asyncio
import json

from app.agents.multi_agent import _parse_steps, planner_executor_verifier
from app.models.schemas import RentRequirement


class FakeChat:
    """fake LLM：Planner 返回固定 steps，Verifier 返回 verdict。"""

    def __init__(self, steps, verdict):
        self._steps = steps
        self._verdict = verdict
        self.planner_calls = 0
        self.verifier_calls = 0

    async def __call__(self, messages):
        sys = messages[0]["content"]
        if sys.startswith("你是 RentAI 的 Planner"):
            self.planner_calls += 1
            return json.dumps(self._steps)
        self.verifier_calls += 1
        return self._verdict


def test_parse_steps():
    s = _parse_steps('[{"step":1,"action":"检索滨湖房源"},{"step":2,"action":"筛选户型"}]')
    assert len(s) == 2 and s[1]["action"] == "筛选户型"


def test_parse_steps_tolerates_wrapped_text():
    # 模型偶发在 JSON 外包文字，应能截取
    s = _parse_steps('下面是计划：\n[{"step":1,"action":"a"}]\n请执行')
    assert len(s) == 1 and s[0]["action"] == "a"


async def fake_execute(req):
    return ([], None)  # (trace, viewing) 空结果，验证 verify 处理 None


def test_planner_executor_verifier_orchestration():
    fake = FakeChat([{"step": 1, "action": "检索滨湖 3000 内房源"}], "已达成")
    req = RentRequirement(district="滨湖", max_price=3000, room_types=["1室"])
    out = asyncio.run(planner_executor_verifier(req, chat=fake, execute=fake_execute))
    # Planner 与 Verifier 各调一次（角色分工）
    assert fake.planner_calls == 1 and fake.verifier_calls == 1
    assert len(out["steps"]) == 1
    assert out["steps"][0]["action"].startswith("检索")
    assert out["verify"]["achieved"] is True
    assert out["verify"]["verdict"] == "已达成"
    assert out["viewing"] is None  # fake 空执行结果


def test_verifier_missing_verdict():
    fake = FakeChat([{"step": 1, "action": "检索房源"}], "缺失：未覆盖滨湖区域")
    req = RentRequirement(district="滨湖", max_price=2000)
    out = asyncio.run(planner_executor_verifier(req, chat=fake, execute=fake_execute))
    assert out["verify"]["achieved"] is False
    assert "缺失" in out["verify"]["verdict"]
