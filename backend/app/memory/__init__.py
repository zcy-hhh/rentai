# 作者：zcy
"""三层记忆系统（参考 Dify 源码设计重构）。

设计来源：Dify api/models/model.py 的 conversations / messages / message_agent_thoughts 表，
以及 Dify 的 token 反向累计修剪策略（从最新消息往前累加 token，超 max_tokens 截断）。

三层记忆：
1. **工作记忆（Working Memory）**：进程内存 / LangGraph State，单次请求内有效，请求结束释放。
2. **短期记忆（Short-term Memory）**：PG conversations + messages 表，session_id 隔离，
   无 TTL 永久保存（用户删除才清除），Redis 做热缓存。上下文修剪用 token 反向累计。
3. **长期记忆（Long-term Memory）**：PG user_profiles 表，user_id 隔离，无 TTL，
   upsert 更新（事实覆盖而非追加），跨会话共享。

与旧实现的区别：旧版会话和画像都存 Redis 带 TTL（1天/7天），会导致"明天东西就没了"。
新版全部 PG 持久化无 TTL，Redis 只做缓存，数据永不丢失。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentThought, Conversation, Message, UserProfile
from app.db.session import SessionLocal

# ---- 上下文修剪参数（参考 Dify：最多 2000 tokens / 500 条消息）----
MAX_HISTORY_TOKENS = 2000
MAX_HISTORY_MESSAGES = 500


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def estimate_tokens(text: str) -> int:
    """粗估 token 数：中文 1 字 ≈ 1.5 token，英文 1 词 ≈ 1.3 token。

    不依赖 tiktoken（避免额外依赖），用于上下文修剪的预算判断，精度足够。
    """
    if not text:
        return 0
    cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cn
    return int(cn * 1.5 + other * 0.5)


def trim_history(messages: list[dict], max_tokens: int = MAX_HISTORY_TOKENS) -> list[dict]:
    """token 反向累计修剪（参考 Dify 源码逻辑）。

    从最新消息往前累加 token，超过 max_tokens 就截断，保留最新的消息。
    这样保证最近的上下文完整，旧的被压缩/丢弃。

    Dify 源码逻辑（还原）：
        for msg in reversed(messages):
            tokens = count_tokens(msg.content)
            if total_tokens + tokens > max_token_limit: break
            memory.insert(0, msg)
    """
    result: list[dict] = []
    total = 0
    for msg in reversed(messages):
        t = estimate_tokens(msg.get("content", ""))
        if total + t > max_tokens and result:
            break
        result.insert(0, msg)
        total += t
        if len(result) >= MAX_HISTORY_MESSAGES:
            break
    return result


# ============ 短期记忆：会话 + 消息 ============

async def get_or_create_conversation(session_id: str, user_id: str) -> Conversation:
    """获取或创建会话（幂等）。"""
    async with SessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == session_id,
                Conversation.is_deleted == False,  # noqa: E712
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv
        conv = Conversation(id=session_id, user_id=user_id, title="新对话")
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv


async def append_message(
    session_id: str,
    role: str,
    content: str,
    tokens: int = 0,
    latency_ms: int = 0,
    tool_calls: dict | None = None,
) -> Message:
    """追加一条消息到会话（短期记忆持久化）。"""
    async with SessionLocal() as db:
        msg = Message(
            conversation_id=session_id,
            role=role,
            content=content,
            tokens=tokens or estimate_tokens(content),
            latency_ms=latency_ms,
            tool_calls=tool_calls or {},
        )
        db.add(msg)
        # 更新会话的对话计数和时间
        await db.execute(
            Conversation.__table__.update()
            .where(Conversation.id == session_id)
            .values(dialogue_count=Conversation.dialogue_count + 1, updated_at=_now())
        )
        await db.commit()
        await db.refresh(msg)
        return msg


async def get_history(session_id: str, max_tokens: int = MAX_HISTORY_TOKENS) -> list[dict]:
    """读取会话历史并做 token 修剪（返回给 LLM 的上下文）。

    从 PG 读全部消息 → 按时间排序 → token 反向累计修剪 → 返回 [(role, content), ...]。
    """
    async with SessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == session_id)
            .order_by(Message.created_at.asc())
        )
        msgs = result.scalars().all()
    raw = [{"role": m.role, "content": m.content} for m in msgs]
    return trim_history(raw, max_tokens)


async def list_conversations(user_id: str) -> list[dict]:
    """列出用户的所有会话（用于前端会话列表）。"""
    async with SessionLocal() as db:
        result = await db.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_deleted == False,  # noqa: E712
            )
            .order_by(Conversation.updated_at.desc())
        )
        convs = result.scalars().all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "dialogue_count": c.dialogue_count,
            "updated_at": c.updated_at.isoformat() if c.updated_at else "",
        }
        for c in convs
    ]


async def delete_conversation(session_id: str) -> None:
    """软删除会话（参考 Dify 的 is_deleted 设计，不物理删除）。"""
    async with SessionLocal() as db:
        await db.execute(
            Conversation.__table__.update()
            .where(Conversation.id == session_id)
            .values(is_deleted=True, updated_at=_now())
        )
        await db.commit()


# ============ 长期记忆：用户画像 ============

async def get_profile(user_id: str) -> dict:
    """读取用户画像（长期记忆）。不存在返回空 dict。"""
    async with SessionLocal() as db:
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        prof = result.scalar_one_or_none()
    if not prof:
        return {}
    return {
        "districts": prof.districts or [],
        "budgets": prof.budgets or [],
        "room_types": prof.room_types or [],
        "tags": prof.tags or [],
    }


async def update_profile(user_id: str, patch: dict) -> dict:
    """upsert 更新用户画像（长期记忆）。

    参考 Dify 的事实更新策略：区域/户型/标签去重追加，预算保留最近3个，
    不是简单覆盖也不是无限追加。
    """
    async with SessionLocal() as db:
        result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        prof = result.scalar_one_or_none()
        if not prof:
            prof = UserProfile(user_id=user_id, districts=[], budgets=[], room_types=[], tags=[])
            db.add(prof)
            await db.flush()
        # 去重合并
        if patch.get("districts"):
            merged = list(dict.fromkeys([*prof.districts, *patch["districts"]]))
            prof.districts = merged[-10:]  # 最多保留10个区域
        if patch.get("budgets"):
            merged = [*prof.budgets, *patch["budgets"]]
            prof.budgets = merged[-3:]  # 保留最近3个预算区间
        if patch.get("room_types"):
            merged = list(dict.fromkeys([*prof.room_types, *patch["room_types"]]))
            prof.room_types = merged[-5:]
        if patch.get("tags"):
            merged = list(dict.fromkeys([*prof.tags, *patch["tags"]]))
            prof.tags = merged[-10:]
        prof.updated_at = _now()
        await db.commit()
        await db.refresh(prof)
    return await get_profile(user_id)


def profile_text(p: dict) -> str:
    """把用户画像渲染成注入 System Prompt 的文字。"""
    if not p:
        return "（新用户，暂无画像）"
    parts = []
    if p.get("districts"):
        parts.append("常用区域：" + "、".join(p["districts"]))
    if p.get("budgets"):
        parts.append("常用预算区间：" + "、".join(f"{a}-{b}元" for a, b in p["budgets"][-3:]))
    if p.get("room_types"):
        parts.append("常用户型：" + "、".join(p["room_types"]))
    if p.get("tags"):
        parts.append("偏好：" + "、".join(p["tags"]))
    return "；".join(parts) if parts else "（画像正在积累）"


# ============ Agent 思考过程持久化 ============

async def save_agent_thought(
    message_id: str, position: int, thought: str,
    tool: str = "", tool_input: dict | None = None, observation: str = "",
) -> None:
    """保存 Agent 一步思考过程（参考 Dify message_agent_thoughts 表）。"""
    async with SessionLocal() as db:
        t = AgentThought(
            message_id=message_id,
            position=position,
            thought=thought,
            tool=tool,
            tool_input=tool_input or {},
            observation=observation,
        )
        db.add(t)
        await db.commit()


async def get_agent_thoughts(message_id: str) -> list[dict]:
    """读取某条消息关联的 Agent 思考链路（用于调试和可观测性展示）。"""
    async with SessionLocal() as db:
        result = await db.execute(
            select(AgentThought)
            .where(AgentThought.message_id == message_id)
            .order_by(AgentThought.position.asc())
        )
        thoughts = result.scalars().all()
    return [
        {
            "position": t.position,
            "thought": t.thought,
            "tool": t.tool,
            "tool_input": t.tool_input,
            "observation": t.observation,
        }
        for t in thoughts
    ]


# ============ 建表（启动时调用）============

async def create_memory_tables() -> None:
    """创建记忆相关表（如果不存在）。在应用启动时调用一次。"""
    from app.db.models import Base
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Conversation.__table__,
                    Message.__table__,
                    AgentThought.__table__,
                    UserProfile.__table__,
                ],
            )
        )
