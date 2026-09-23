# 作者：zcy
"""ORM 模型：房源 / 用户 / 看房清单 / 审计日志（PostgreSQL + pgvector）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Listing(Base):
    """房源：18 套 mock 数据迁移到 PG，含 1024 维 pgvector 向量列用于 RAG 检索。"""

    __tablename__ = "listings"

    # pgvector HNSW 余弦索引（近似最近邻，加速向量检索）
    __table_args__ = (
        Index(
            "idx_listings_hnsw", "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(50), default="mock")
    url: Mapped[str] = mapped_column(String(500), default="")
    district: Mapped[str] = mapped_column(String(50), index=True)
    address: Mapped[str] = mapped_column(String(200))
    price: Mapped[int] = mapped_column(Integer)
    area: Mapped[int] = mapped_column(Integer)
    room_type: Mapped[str] = mapped_column(String(20))
    orientation: Mapped[str] = mapped_column(String(20))
    floor: Mapped[str] = mapped_column(String(30))
    facilities: Mapped[list] = mapped_column(JSON, default=list)
    listing_date: Mapped[str] = mapped_column(String(20))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class User(Base):
    """用户：认证 + RBAC 角色 + 多租户。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Viewing(Base):
    """看房清单：HITL 状态机持久化（pending/confirmed/adjusted）。"""

    __tablename__ = "viewings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    listing_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # ViewingList 完整数据（持久化恢复用）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    """审计日志：多租户下的关键操作留痕（登录 / 生成清单 / 确认 / 调整）。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DocChunk(Base):
    """多模态文档知识库：PDF/PPT/Excel 等文档切块后的向量块（可引用溯源）。

    复用 pgvector：embedding 存 VECTOR(1024)，HNSW 余弦索引；text 为原文块，
    带来源文档/页码/块号元数据，检索返回带引用的原文（防幻觉）。
    """

    __tablename__ = "doc_chunks"

    __table_args__ = (
        Index(
            "idx_doc_chunks_hnsw", "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String, index=True)     # 文档标识
    source_name: Mapped[str] = mapped_column(String(200))       # 原文件名
    page: Mapped[int] = mapped_column(Integer, default=0)       # 页码/页号
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)  # 块序号
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector(1024), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---- 参考 Dify 的记忆系统：会话/消息/Agent思考/用户画像，全部 PG 持久化无 TTL ----

class Conversation(Base):
    """会话表（参考 Dify conversations 表）：短期记忆的持久化载体。

    与 Dify 一致：无 TTL，用户不删除就永久存在；is_deleted 软删除。
    Redis 只做热缓存，PG 是真相源。
    """

    __tablename__ = "conversations"

    __table_args__ = (
        Index("idx_conv_user", "user_id", "updated_at"),
        Index("idx_conv_user_active", "user_id", "is_deleted", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)          # session_id
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    summary: Mapped[str] = mapped_column(Text, default="")             # 对话摘要（长期记忆素材）
    mode: Mapped[str] = mapped_column(String(32), default="auto")      # workflow/react/auto
    dialogue_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    """消息表（参考 Dify messages 表）：会话内每轮对话的持久化。

    关键字段：tokens（token 计数，用于上下文修剪）、latency_ms（响应延迟，可观测性）、
    tool_calls（工具调用记录，审计与回溯）。
    """

    __tablename__ = "messages"

    __table_args__ = (
        Index("idx_msg_conv", "conversation_id", "created_at"),
        Index("idx_msg_user", "conversation_id", "role"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String(16))    # user / assistant / system
    content: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer, default=0)           # token 计数（修剪用）
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)       # 响应延迟（可观测）
    tool_calls: Mapped[dict] = mapped_column(JSON, default=dict)      # 工具调用记录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentThought(Base):
    """Agent 思考过程表（参考 Dify message_agent_thoughts 表）。

    ReAct 每一步的 thought / tool / tool_input / observation 都持久化，
    支持回溯 Agent 决策链路、调试、可观测性。position 标记步骤序号。
    """

    __tablename__ = "agent_thoughts"

    __table_args__ = (
        Index("idx_thought_msg", "message_id", "position"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(String, index=True)       # 关联 messages.id
    position: Mapped[int] = mapped_column(Integer)                    # 步骤序号
    thought: Mapped[str] = mapped_column(Text, default="")            # 推理过程
    tool: Mapped[str] = mapped_column(String(64), default="")         # 调用的工具名
    tool_input: Mapped[dict] = mapped_column(JSON, default=dict)      # 工具输入参数
    observation: Mapped[str] = mapped_column(Text, default="")        # 工具返回结果
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class UserProfile(Base):
    """用户画像表（长期记忆，参考 Dify 持久化设计）：无 TTL，upsert 更新。

    存用户的区域/预算/户型/标签偏好，跨会话共享。每次执行需求或确认清单后自动并入。
    与 Dify 的 Conversation Variables + Memory feature 对应：结构化偏好永久保存，
    事实更新时覆盖而非追加（防止无限膨胀）。
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    districts: Mapped[list] = mapped_column(JSON, default=list)       # 常用区域（去重）
    budgets: Mapped[list] = mapped_column(JSON, default=list)         # 预算区间列表（保留最近3个）
    room_types: Mapped[list] = mapped_column(JSON, default=list)      # 户型偏好（去重）
    tags: Mapped[list] = mapped_column(JSON, default=list)            # 标签偏好（去重）
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
