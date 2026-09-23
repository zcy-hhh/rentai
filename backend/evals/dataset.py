# 作者：zcy
"""评测集：标注的租房匹配用例 + 避坑召回用例。

每条用例标注"应命中的房源 id"（expected），用于计算匹配准确率/召回率；
坑房源标注"应命中的风险类型"，用于计算避坑召回率。
"""
from __future__ import annotations

from typing import Any

# 匹配用例：需求 → 应命中房源（基于 mock 数据的硬条件计算）
MATCH_CASES: list[dict[str, Any]] = [
    {"name": "滨湖·一居·预算4k", "requirement": {"district": "滨湖", "max_price": 4000, "room_types": ["1室"]},
     "expected": ["mock-005"]},
    {"name": "滨湖·两居·预算6k", "requirement": {"district": "滨湖", "max_price": 6000, "room_types": ["2室"]},
     "expected": ["mock-004"]},
    {"name": "新吴·一居·预算6k", "requirement": {"district": "新吴", "max_price": 6000, "room_types": ["1室"]},
     "expected": ["mock-013", "mock-015"]},
    {"name": "锡山·两居·预算4k", "requirement": {"district": "锡山", "max_price": 4000, "room_types": ["2室"]},
     "expected": ["mock-011", "mock-012"]},
    {"name": "梁溪·一居·预算4k", "requirement": {"district": "梁溪", "max_price": 4000, "room_types": ["1室"]},
     "expected": ["mock-007", "mock-009"]},
    {"name": "河西·两居·预算4k", "requirement": {"district": "河西", "max_price": 4000, "room_types": ["2室"]},
     "expected": ["mock-002"]},
]

# 避坑用例：坑房源 → 应命中的风险类型
RISK_CASES: list[dict[str, Any]] = [
    {"name": "新吴低价单间", "listing_id": "mock-015",
     "expected_risks": ["疑似群租", "疑似虚假房源"]},
    {"name": "锡山远郊大两居", "listing_id": "mock-012",
     "expected_risks": ["通勤偏远"]},
]
