"""扫描哪些房源能触发各类风险，用于构造避坑评测用例。"""
import sys
sys.path.insert(0, ".")
from app.models.schemas import RentRequirement
from app.tools.listing_source import get_sources
from app.rag.retriever import retrieve_risks
from collections import defaultdict

req = RentRequirement(max_price=99999)
all_listings = []
for src in get_sources():
    all_listings.extend(src.search(req))

district_prices = defaultdict(list)
for l in all_listings:
    district_prices[l.district].append(l.price)
district_avg = {d: sum(v)/len(v) for d, v in district_prices.items()}

risk_examples = defaultdict(list)
for l in all_listings:
    avg = district_avg.get(l.district)
    risks = retrieve_risks(l, district_avg_price=avg)
    for r in risks:
        risk_examples[r.kind].append((l.id, l.title, l.district, l.price, l.orientation, l.facilities[:3]))

for kind, examples in sorted(risk_examples.items()):
    print(f"\n{kind} ({len(examples)}套):")
    for ex in examples[:3]:
        print(f"  {ex[0]} | {ex[1]} | {ex[2]} | ¥{ex[3]} | 朝{ex[4]} | {ex[5]}")

print(f"\n总房源: {len(all_listings)}")
