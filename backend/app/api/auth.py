# 作者：zcy
"""认证路由：登录签发 token、查询当前用户（受保护）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.core.users import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant: str


class MeResponse(BaseModel):
    username: str
    role: str
    tenant: str


@router.post("/login", response_model=LoginResponse, summary="登录获取 token")
def login(body: LoginRequest) -> LoginResponse:
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username, user.role, user.tenant_id)
    return LoginResponse(access_token=token, role=user.role, tenant=user.tenant_id)


@router.get("/me", response_model=MeResponse, summary="当前用户信息（需 Bearer token）")
def me(user: dict = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user["sub"], role=user["role"], tenant=user["tenant"])
