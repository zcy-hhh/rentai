# 作者：zcy
"""应用配置：通过 .env / 环境变量加载，密钥不入库不入代码。"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 基础
    app_name: str = "RentAI"
    env: str = "dev"
    api_prefix: str = "/api"

    # LLM：阿里云百炼（DashScope，OpenAI 兼容）
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "gte-rerank"

    # 高德开放平台（Web 服务）：POI 检索 / 地理编码 / 通勤
    amap_key: str = ""

    # 数据层
    database_url: str = "postgresql+asyncpg://rent:rent@localhost:5432/rentai"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    # 认证
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
