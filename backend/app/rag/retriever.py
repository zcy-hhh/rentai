# 作者：zcy
"""避坑检索器：混合检索（结构化关键词 + 可选向量语义），返回带引用的风险标注。

M2 阶段：基于确定性规则/关键词检索（可复现、可评测），每条标注带 reference。
M4 阶段：叠加 embedding 语义检索 + rerank（百炼 gte-rerank）。
"""
from __future__ import annotations

from app.models.schemas import Listing, RiskNote
from app.rag.knowledge_base import check_listing


def retrieve_risks(listing: Listing, district_avg_price: float | None = None) -> list[RiskNote]:
    """对一个候选房源执行避坑检查，返回风险标注（带引用）。"""
    return check_listing(listing, district_avg_price=district_avg_price)
