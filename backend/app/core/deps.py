# 作者：zcy
"""依赖注入：当前用户解析 + RBAC 权限校验 + 多租户隔离。"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header, HTTPException

from app.core import security

_ROLE_WEIGHT = {"user": 1, "admin": 2, "audit": 3}


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer token")
    token = authorization[7:]
    try:
        return security.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="token 无效或已过期")


def require_role(*roles: str) -> Callable:
    """RBAC：要求当前用户具备指定角色之一。"""

    def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"角色 {user['role']} 无权限，需要 {roles}")
        return user

    return dep


def require_tenant(user: dict = Depends(get_current_user)) -> str:
    """多租户：返回当前租户 id（后续所有数据查询按 tenant 过滤）。"""
    return user["tenant"]
