# 作者：zcy
"""合成房源数据生成 CLI 入口（逻辑在 app.db.synthetic，此处仅打印示例与统计）。

用法：uv run python scripts/synthetic_data.py
      from scripts.synthetic_data import generate_synthetic  # 兼容旧调用
"""
from __future__ import annotations

from app.db.synthetic import DISTRICTS, generate_synthetic  # noqa: F401  re-export

if __name__ == "__main__":
    from collections import Counter

    data = generate_synthetic(200)
    print(f"共 {len(data)} 套合成房源（source=synthetic）")
    print("区分布:", dict(Counter(d["district"] for d in data)))
    print("户型分布:", dict(Counter(d["room_type"] for d in data)))
    print("\n前 3 条示例:")
    for d in data[:3]:
        print(f"  {d['id']} {d['title']} | {d['district']} | ¥{d['price']} | {d['room_type']} | {d['area']}㎡ | 验:{d['is_verified']} | 风险:{d['risk_flags']}")
        print(f"    {d['description']}")
