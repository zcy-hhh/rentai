# 作者：zcy
"""JWT 安全：签发与校验（RBAC 角色 + 多租户 tenant_id 进 token）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def create_access_token(subject: str, role: str, tenant_id: str) -> str:
    """签发 token：sub=用户, role=角色, tenant=租户, 带过期时间。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "tenant": tenant_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """校验并解码 token，非法/过期抛异常。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
