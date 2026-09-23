# 作者：zcy
"""业务数据模型：租房需求、房源、候选房源、风险标注、看房清单（统一 Schema）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RentRequirement(BaseModel):
    """用户租房需求。"""
    district: Optional[str] = Field(default=None, description="意向区域")
    max_price: float = Field(..., gt=0, description="最高月租金（元）")
    min_area: Optional[float] = Field(default=None, gt=0, description="最小面积（㎡）")
    room_types: list[str] = Field(default_factory=lambda: ["1室", "2室", "3室"], description="可接受户型")
    commute_to: Optional[str] = Field(default=None, description="通勤目的地")
    commute_max_minutes: Optional[int] = Field(default=None, description="通勤时间上限（分钟）")
    tags: list[str] = Field(default_factory=list, description="偏好标签，如 ['近地铁','精装','朝南']")
    user_note: Optional[str] = Field(default=None, description="用户补充的自由指令（供 Agent 自主决策）")


class Listing(BaseModel):
    """标准化的房源（来自任意数据源，统一结构）。"""
    id: str
    title: str
    source: str
    url: str = ""
    district: str
    address: str = ""
    price: float
    area: float
    room_type: str
    orientation: str = ""
    floor: str = ""
    facilities: list[str] = Field(default_factory=list)
    listing_date: str = ""
    is_verified: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    description: str = ""


class RiskNote(BaseModel):
    """避坑风险标注（可追溯：必须带引用依据）。"""
    kind: str = Field(description="风险类型，如 押金/合同/虚假房源/费用/房况")
    severity: str = Field(description="严重等级：高/中/低")
    reason: str = Field(description="依据说明")
    reference: str = Field(description="引用原文/依据来源")
    suggestion: str = Field(default="", description="应对建议")


class CandidateListing(Listing):
    """带评分、理由、风险标注与通勤的候选房源。"""
    match_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
    risks: list[RiskNote] = Field(default_factory=list)
    commute_minutes: Optional[float] = Field(default=None, description="通勤估算分钟")


class ViewingList(BaseModel):
    """看房清单（HITL 产物）。"""
    list_id: str
    requirement: RentRequirement
    candidates: list[CandidateListing]
    verify_items: list[str] = Field(default_factory=list, description="现场需核实项")
    ask_items: list[str] = Field(default_factory=list, description="问询房东/中介的问题清单")
    status: str = Field(default="pending", description="pending/confirmed")


class RentResponse(BaseModel):
    requirement: RentRequirement
    total_matched: int
    candidates: list[CandidateListing]


class ConfirmRequest(BaseModel):
    list_id: str
    action: str = Field(default="confirm", description="confirm/adjust")
    note: str = Field(default="", description="确认备注（审计留痕）")
    user_id: str = Field(default="demo", description="操作人（用于并入用户画像偏好）")


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户自然语言消息")
    session_id: str = Field(default="default", description="会话标识（多轮上下文/短期记忆）")
    user_id: str = Field(default="demo", description="用户标识（长期画像）")
    history: Optional[list[tuple[str, str]]] = Field(
        default=None,
        description="前端携带的完整对话历史 [(role, content), ...]，作为上下文真相源；缺省时回退 Redis 会话记忆",
    )

