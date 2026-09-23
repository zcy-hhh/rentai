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
