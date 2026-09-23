# 作者：zcy
"""FastAPI 应用入口。"""
from __future__ import annotations

from fastapi import FastAPI

from app.api import auth
from app.api.routes import router
from app.core.config import settings
from app.tools import setup as tools_setup  # noqa: F401  # 启动时注册工具

tools_setup.register_builtin_tools()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="企业级智能租房助手 Agent（RentAI）",
)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.env}
