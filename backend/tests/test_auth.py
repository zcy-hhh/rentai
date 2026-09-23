# 作者：zcy
"""M5 认证测试：JWT 登录、token 校验、受保护端点。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_success() -> None:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"]
    assert data["role"] == "admin"


def test_login_wrong_password() -> None:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token() -> None:
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_valid_token() -> None:
    r = client.post("/api/auth/login", json={"username": "user", "password": "user123"})
    token = r.json()["access_token"]
    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["tenant"] == "tenant-a"
