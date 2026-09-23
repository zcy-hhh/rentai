# 作者：zcy
"""演示用户表（内存，M5b 迁移 PostgreSQL）。含角色与租户。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoUser:
    username: str
    password: str
    role: str       # user / admin / audit
    tenant_id: str


DEMO_USERS: dict[str, DemoUser] = {
    "admin": DemoUser("admin", "admin123", "admin", "tenant-a"),
    "user": DemoUser("user", "user123", "user", "tenant-a"),
    "audit": DemoUser("audit", "audit123", "audit", "tenant-b"),
}


def authenticate(username: str, password: str) -> DemoUser | None:
    u = DEMO_USERS.get(username)
    if u and u.password == password:
        return u
    return None
