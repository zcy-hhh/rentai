"""扫描房源库分布。"""
import sys
sys.path.insert(0, ".")
from app.models.schemas import RentRequirement
from app.tools.listing_source import get_sources
from collections import Counter

req = RentRequirement(max_price=99999)
all_listings = []
for src in get_sources():
    all_listings.extend(src.search(req))

print(f"总房源数: {len(all_listings)}")

districts = Counter(l.district for l in all_listings)
print("\n区域分布:")
for d, c in districts.most_common():
    print(f"  {d}: {c}")

prices = [l.price for l in all_listings if l.price]
print(f"\n价格: min={min(prices)}, max={max(prices)}, avg={sum(prices)/len(prices):.0f}")

rooms = Counter(l.room_type for l in all_listings)
print("\n户型分布:")
for r, c in rooms.most_common():
    print(f"  {r}: {c}")

all_facilities = Counter()
for l in all_listings:
    for f in l.facilities:
        all_facilities[f] += 1
print("\n设施标签分布:")
for f, c in all_facilities.most_common():
    print(f"  {f}: {c}")

metro = [l for l in all_listings if "近地铁" in l.facilities]
print(f"\n近地铁房源: {len(metro)}")
jingzhuang = [l for l in all_listings if "精装" in l.facilities]
print(f"精装房源: {len(jingzhuang)}")

print("\n各区域 <=3000 数量:")
for d in districts:
    cnt = len([l for l in all_listings if l.district == d and l.price <= 3000])
    print(f"  {d}: {cnt}")

print("\n滨湖 1室 <=3000 近地铁:")
cnt = len([l for l in all_listings if l.district == "滨湖" and l.price <= 3000 and "1室" in l.room_type and "近地铁" in l.facilities])
print(f"  {cnt} 套")
