# 作者：zcy
"""避坑知识库：结构化风险规则（确定性、可测试、带引用依据）。

M2 阶段用规则/关键词检索（可复现、可评测）；M4 叠加向量语义检索。
每条规则含 reference（引用依据），用于防幻觉：风险标注必须可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.schemas import Listing, RiskNote


@dataclass(frozen=True)
class RiskRule:
    kind: str
    severity: str                      # 高 / 中 / 低
    keywords: tuple[str, ...]          # 命中关键词（对 description / facilities / risk_flags / orientation）
    reference: str                     # 引用依据
    reason: str
    suggestion: str
    field_names: tuple[str, ...] = ("risk_flags", "facilities", "description", "orientation")  # 检索字段
    max_price_ratio: float | None = None  # 若设置，价格低于"参考均价×ratio"且未验证则触发（疑似虚假房源）


RISK_RULES: list[RiskRule] = [
    RiskRule(
        kind="疑似群租",
        severity="高",
        keywords=("群租", "隔断", "人均面积"),
        reference="平台风险标注 + 群租治理相关规定",
        reason="房源被标注为疑似群租或存在隔断，存在合规与安全风险。",
        suggestion="现场核实是否属于群租，确认房间数与人均面积，避免违规租住。",
    ),
    RiskRule(
        kind="商水商电",
        severity="中",
        keywords=("商水商电", "商用性质", "公寓性质"),
        reference="房源信息字段：水电计价性质",
        reason="该房源为商业水电计价，月成本可能显著高于民用。",
        suggestion="问清水电单价，估算月生活成本是否可接受。",
    ),
    RiskRule(
        kind="朝向采光",
        severity="低",
        keywords=("朝北",),
        reference="房源信息字段：朝向",
        reason="朝北房源采光较差，冬季阴冷。",
        suggestion="看房时在晴天下午实际感受采光。",
    ),
    RiskRule(
        kind="无电梯高楼层",
        severity="中",
        keywords=("无电梯",),
        reference="房源信息字段：楼层与电梯",
        reason="无电梯且楼层较高，日常通勤与搬运不便。",
        suggestion="确认楼层，老人小孩或搬家时需评估。",
    ),
    RiskRule(
        kind="通勤偏远",
        severity="中",
        keywords=("离地铁远", "距地铁", "无地铁"),
        reference="房源信息字段：交通距离",
        reason="房源离地铁/公交较远，通勤成本高。",
        suggestion="实测通勤时间，确认是否有接驳。",
    ),
    RiskRule(
        kind="合同陷阱提示",
        severity="中",
        keywords=("押一付三", "违约金", "转租", "续租"),
        reference="租赁合同常见风险条款（押金、违约金、转租权限）",
        reason="合同可能含押金扣减、高额违约金、限制转租等条款。",
        suggestion="签约前逐条核对押金退还、违约、转租、维修责任条款。",
    ),
    RiskRule(
        kind="中介费提示",
        severity="低",
        keywords=("中介费", "服务费", "佣金"),
        reference="房源信息字段：费用说明",
        reason="可能存在中介费/服务费，需提前确认由谁承担。",
        suggestion="确认中介费比例与承担方，写入合同。",
    ),
    RiskRule(
        kind="疑似虚假房源",
        severity="高",
        keywords=("超低价", "急租", "特价"),
        reference="价格明显低于市场均值 + 平台未验证 → 高可疑",
        reason="价格显著低于区域均价且未经验证，存在虚假/引流房源风险。",
        suggestion="优先联系平台验证房源真实性，警惕先交定金再引导换房。",
        max_price_ratio=0.7,
    ),
]


def _extract_searchable_text(listing: Listing) -> str:
    """把所有可检索字段拼成文本，用于关键词命中。"""
    parts = [listing.description, *listing.risk_flags, *listing.facilities, listing.orientation, listing.floor]
    return " ".join(p for p in parts if p)


def check_listing(listing: Listing, district_avg_price: float | None = None) -> list[RiskNote]:
    """对一个房源跑全部风险规则，返回命中的风险标注（带引用）。"""
    text = _extract_searchable_text(listing)
    notes: list[RiskNote] = []
    for rule in RISK_RULES:
        hit = False
        # 结构化字段关键词命中
        if any(kw in text for kw in rule.keywords):
            hit = True
        # 疑似虚假：价格异常 + 未验证
        if rule.max_price_ratio is not None and district_avg_price:
            if not listing.is_verified and listing.price < district_avg_price * rule.max_price_ratio:
                hit = True
        if hit:
            notes.append(
                RiskNote(
                    kind=rule.kind,
                    severity=rule.severity,
                    reason=rule.reason,
                    reference=rule.reference,
                    suggestion=rule.suggestion,
                )
            )
    return notes
