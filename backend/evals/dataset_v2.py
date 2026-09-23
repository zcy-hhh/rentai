# 作者：zcy
"""真实评测集：基于235套房源构造多样化用例，跑出可信指标。

匹配用例：覆盖不同区域/价格/户型/标签组合 + 边界情况 + 空结果用例
避坑用例：覆盖不同风险类型
Agent决策用例：覆盖明确需求/信息不足/闲聊/增量/修改
"""
from __future__ import annotations
from typing import Any

# ============ 匹配用例（20条） ============
# expected 通过独立 ground truth 函数计算，不硬编码
MATCH_CASES: list[dict[str, Any]] = [
    # 基础单条件
    {"name": "滨湖不限户型5k内", "requirement": {"district": "滨湖", "max_price": 5000, "room_types": []}},
    {"name": "梁溪1室3k内", "requirement": {"district": "梁溪", "max_price": 3000, "room_types": ["1室"]}},
    {"name": "惠山2室4k内", "requirement": {"district": "惠山", "max_price": 4000, "room_types": ["2室"]}},
    {"name": "新吴3室6k内", "requirement": {"district": "新吴", "max_price": 6000, "room_types": ["3室"]}},
    {"name": "锡山1室2500内", "requirement": {"district": "锡山", "max_price": 2500, "room_types": ["1室"]}},
    # 多户型
    {"name": "滨湖1室或2室4k内", "requirement": {"district": "滨湖", "max_price": 4000, "room_types": ["1室", "2室"]}},
    {"name": "梁溪2室或3室5k内", "requirement": {"district": "梁溪", "max_price": 5000, "room_types": ["2室", "3室"]}},
    # 标签过滤
    {"name": "滨湖1室3k内近地铁", "requirement": {"district": "滨湖", "max_price": 3000, "room_types": ["1室"], "tags": ["近地铁"]}},
    {"name": "梁溪2室4k内精装", "requirement": {"district": "梁溪", "max_price": 4000, "room_types": ["2室"], "tags": ["精装"]}},
    {"name": "惠山1室3k内近地铁精装", "requirement": {"district": "惠山", "max_price": 3000, "room_types": ["1室"], "tags": ["近地铁", "精装"]}},
    {"name": "新吴2室5k内电梯", "requirement": {"district": "新吴", "max_price": 5000, "room_types": ["2室"], "tags": ["电梯"]}},
    # 跨区域（不限区域）
    {"name": "全市1室2k内", "requirement": {"district": None, "max_price": 2000, "room_types": ["1室"]}},
    {"name": "全市2室3500内近地铁", "requirement": {"district": None, "max_price": 3500, "room_types": ["2室"], "tags": ["近地铁"]}},
    # 边界价格
    {"name": "滨湖1室价格刚好2000", "requirement": {"district": "滨湖", "max_price": 2000, "room_types": ["1室"]}},
    {"name": "梁溪3室价格刚好8000", "requirement": {"district": "梁溪", "max_price": 8000, "room_types": ["3室"]}},
    # 最小面积
    {"name": "滨湖2室4k内最小40平", "requirement": {"district": "滨湖", "max_price": 4000, "room_types": ["2室"], "min_area": 40}},
    {"name": "惠山1室3k内最小30平", "requirement": {"district": "惠山", "max_price": 3000, "room_types": ["1室"], "min_area": 30}},
    # 空结果（条件过于苛刻）
    {"name": "滨湖1室500内（应空）", "requirement": {"district": "滨湖", "max_price": 500, "room_types": ["1室"]}},
    {"name": "宜兴3室1k内（应空）", "requirement": {"district": "宜兴", "max_price": 1000, "room_types": ["3室"]}},
    {"name": "滨湖1室1k内精装电梯近地铁（应空）", "requirement": {"district": "滨湖", "max_price": 1000, "room_types": ["1室"], "tags": ["精装", "电梯", "近地铁"]}},
]

# ============ 避坑用例（6条，覆盖6种风险类型） ============
RISK_CASES: list[dict[str, Any]] = [
    {"name": "朝北房源采光风险", "listing_id": "beike-WX2212893515224973312", "expected_risks": ["朝向采光"]},
    {"name": "无电梯房源风险", "listing_id": "beike-WX2212415198885576704", "expected_risks": ["无电梯高楼层"]},
    {"name": "商水商电风险", "listing_id": "mock-003", "expected_risks": ["商水商电"]},
    {"name": "低价未验证虚假风险", "listing_id": "mock-012", "expected_risks": ["疑似虚假房源"]},
    {"name": "小面积多房间群租风险", "listing_id": "mock-015", "expected_risks": ["疑似群租"]},
    {"name": "无地铁通勤偏远风险", "listing_id": "beike-WX2211106320747069440", "expected_risks": ["通勤偏远"]},
]

# ============ Agent 决策用例（8条） ============
AGENT_DECISION_CASES: list[dict[str, Any]] = [
    {"name": "明确需求应执行", "message": "我想在滨湖区租个1室，预算3000以内", "expected_kind": "result"},
    {"name": "信息不足应澄清", "message": "我要租房", "expected_kind": "clarify"},
    {"name": "只有区域应澄清", "message": "我想在梁溪区租房", "expected_kind": "clarify"},
    {"name": "闲聊应直接回复", "message": "你好，你能做什么？", "expected_kind": "message"},
    {"name": "感谢应直接回复", "message": "谢谢", "expected_kind": "message"},
    {"name": "增量条件应执行", "message": "还要近地铁的", "expected_kind": "result", "history": [("user", "我想在滨湖区租房，预算3000以内，要1室的"), ("assistant", "已为你找到9套")]},
    {"name": "修改预算应执行", "message": "预算提到4000吧", "expected_kind": "result", "history": [("user", "我想在滨湖区租房，预算3000以内，要1室的"), ("assistant", "已为你找到9套")]},
    {"name": "模糊需求应澄清", "message": "找个便宜点的房子", "expected_kind": "clarify"},
]
