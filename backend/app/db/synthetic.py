# 作者：zcy
"""合成房源数据生成（运行时包内，供数据源与评测复用）。

方案 C：基于无锡各区真实租金水平构造中文风格合成房源。
- 明确标注 source="synthetic"（非真实房源，仅用于链路验证与评测）。
- 固定随机种子，可复现、可评测。
"""
from __future__ import annotations

import random
from typing import Any

# ---- 配置（真实租金梯度，单位：元/月）----
DISTRICTS = {
    "梁溪": {"1室": (2200, 4200), "2室": (3000, 6000), "3室": (4000, 8200)},
    "滨湖": {"1室": (2000, 4600), "2室": (2800, 6500), "3室": (3600, 8500)},
    "新吴": {"1室": (1600, 3600), "2室": (2400, 5400), "3室": (3200, 7000)},
    "锡山": {"1室": (1500, 3400), "2室": (2400, 5200), "3室": (3200, 6800)},
    "惠山": {"1室": (1400, 3200), "2室": (2200, 4800), "3室": (3000, 6200)},
}

ORIENTATIONS = ["朝南", "朝北", "南北", "朝东", "朝西"]
FACILITY_POOL = {
    "1室": [["近地铁", "精装", "家电齐全", "电梯"], ["近地铁", "电梯"], ["精装", "电梯"], ["整租", "近地铁"], ["家电齐全"]],
    "2室": [["近地铁", "电梯", "精装", "整租"], ["有燃气", "整租"], ["近地铁", "电梯"], ["电梯", "精装"], ["整租", "有燃气", "近地铁"]],
    "3室": [["近地铁", "电梯", "精装", "车位"], ["有燃气", "电梯", "整租"], ["精装", "电梯", "车位"], ["整租", "近地铁", "电梯"]],
}
RISK_POOL = [
    [], [], [], [],
    ["商水商电"], ["无电梯"], ["朝北"], ["合租"],
    ["离地铁远"], ["商水商电", "朝北"], ["无电梯", "朝北"],
]
DESC_POOL = [
    "精装，拎包入住，采光好。", "近地铁，通勤方便。", "整租，价格实惠。",
    "商水商电，适合短租。", "朝北，冬暖需开空调。", "无电梯，楼层偏高需爬楼。",
    "合租单间，带独立卫生间。", "离地铁较远，建议公交接驳。", "超低价急租，价格低于市场。",
    "群租改造，隔断较多，谨慎。", "家电齐全，南北通透。", "近产业园，上班方便。",
]
ROAD_POOL = ["文化广场", "湖滨路", "映月湖", "中山路", "清名桥", "青年路", "创想路", "永安里", "春潮路", "太湖大道"]

LOW_PRICE_RATIO = 0.12


def generate_synthetic(count: int = 200, seed: int = 42) -> list[dict[str, Any]]:
    """生成 count 套中文风格合成房源（可复现）。"""
    rng = random.Random(seed)
    listings: list[dict[str, Any]] = []
    districts = list(DISTRICTS.keys())

    for i in range(count):
        district = rng.choice(districts)
        room_type = rng.choice(["1室", "2室", "3室"])
        lo, hi = DISTRICTS[district][room_type]
        price = rng.randint(lo, hi)
        low_price = rng.random() < LOW_PRICE_RATIO
        if low_price:
            price = int(lo * 0.5 + rng.randint(0, int(lo * 0.3)))
        area = {
            "1室": rng.randint(18, 55),
            "2室": rng.randint(50, 95),
            "3室": rng.randint(70, 140),
        }[room_type]
        orientation = rng.choice(ORIENTATIONS)
        floor = f"{rng.choice(['低', '中', '高'])}/{rng.randint(6, 30)}"
        facilities = list(rng.choice(FACILITY_POOL[room_type]))
        is_verified = rng.random() < 0.7
        risk_flags = list(rng.choice(RISK_POOL))
        description = rng.choice(DESC_POOL)
        if low_price:
            is_verified = False
            description = "超低价急租，" + description
        for f in risk_flags:
            if f == "商水商电" and "商水商电" not in description:
                description = "商水商电，" + description
            if f == "朝北" and "朝北" not in description:
                description = "朝北，" + description
            if f == "离地铁远" and "离地铁" not in description:
                description = "离地铁较远，" + description
            if f == "合租" and "合租" not in description:
                description = "合租单间，" + description
        listings.append({
            "id": f"syn-{i:03d}",
            "title": f"{district}·{rng.choice(['万科', '保利', '中海', '绿地', '华润', '金地', '龙湖', '融创'])}小区 {room_type}",
            "source": "synthetic",
            "url": f"https://synthetic/syn-{i:03d}",
            "district": district,
            "address": f"{district}区{rng.choice(ROAD_POOL)}{rng.randint(1, 200)}号",
            "price": price,
            "area": area,
            "room_type": room_type,
            "orientation": orientation,
            "floor": floor,
            "facilities": facilities,
            "listing_date": f"2026-09-{rng.randint(1, 22):02d}",
            "is_verified": is_verified,
            "risk_flags": risk_flags,
            "description": description,
        })
    return listings
