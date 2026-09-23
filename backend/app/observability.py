# 作者：zcy
"""Agent 可观测性（能力地图黄区缺失项之一）。

提供轻量、非侵入的请求级指标：LLM 调用次数、token 用量、延迟、估算成本、Agent 重试轮数。
- **请求级真实数据**：意图解析 LLM 的 prompt/completion tokens（来自百炼 usage）+ 端到端延迟。
- **执行轨迹级**：Agent 重试/反思轮数（1 次初始执行 + 每轮反思 1 次重跑，已在结果里可数）。
- 生产可进一步接 OTel / Langfuse 全链路追踪；这里先保证"请求级真实可复核 + 口径透明"。

成本估算为演示近似，口径明确标注（百炼 qwen-plus 大致单价），不当作精确计费。
"""
from __future__ import annotations

# 演示用近似单价（元/百万 token，口径：qwen-plus 官方公开区间的大致值）
_PROMPT_RATE = 0.8
_COMPLETION_RATE = 2.0


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str = "qwen-plus") -> float:
    """按 token 近似估算本次 LLM 成本（元）。口径：prompt≈0.8 元/百万，completion≈2.0 元/百万。"""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    return round(
        prompt_tokens / 1e6 * _PROMPT_RATE + completion_tokens / 1e6 * _COMPLETION_RATE,
        6,
    )


def build_usage(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    retry_rounds: int,
    extra_llm_calls: int = 0,
    model: str = "qwen-plus",
) -> dict:
    """汇总一次对话轮次的可观测性指标（口径透明地返回给前端展示）。"""
    llm_calls = 1 + extra_llm_calls + retry_rounds  # 意图解析 1 次 + 反思轮数 + 执行重跑轮数（近似）
    return {
        "llm_calls": llm_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "latency_ms": latency_ms,
        "retry_rounds": retry_rounds,
        "est_cost": estimate_cost(prompt_tokens, completion_tokens, model),
        "note": "token 与延迟为意图解析请求级真实值；执行轮数按重试轮数近似，口径见开发记录。",
    }


# ---- 观测指标收集（进程内存累计；生产可换 Redis/TSDB） ----
_METRICS: dict = {
    "chat_turns": 0,
    "llm_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "latency_ms": 0,
    "est_cost": 0.0,
    "retry_rounds": 0,
}


def record_usage(usage: dict | None) -> None:
    """累计一次对话轮次的可观测指标（供观测后台快照）。"""
    if not usage:
        return
    m = _METRICS
    m["chat_turns"] += 1
    m["llm_calls"] += usage.get("llm_calls", 0)
    m["prompt_tokens"] += usage.get("prompt_tokens", 0)
    m["completion_tokens"] += usage.get("completion_tokens", 0)
    m["total_tokens"] += usage.get("total_tokens", 0)
    m["latency_ms"] += usage.get("latency_ms", 0)
    m["est_cost"] += usage.get("est_cost", 0.0)
    m["retry_rounds"] += usage.get("retry_rounds", 0)


def snapshot_metrics() -> dict:
    """观测后台快照：累计指标 + 平均延迟。"""
    m = _METRICS
    turns = m["chat_turns"] or 1
    return {
        **m,
        "avg_latency_ms": round(m["latency_ms"] / turns, 1),
        "note": "进程内存累计，重启归零；生产可换 Redis/TSDB 持久化。",
    }


async def get_db_metrics() -> dict:
    """从 PG messages 表读取持久化观测指标（参考 Dify messages 表的 tokens/latency_ms 字段）。

    与进程内存累计互补：进程内存重启归零，DB 指标永久保存。
    观测后台可同时展示两者，DB 指标作为权威数据源。
    """
    try:
        from app.db.session import async_session
        from app.db.models import Message
        from sqlalchemy import select, func

        async with async_session() as db:
            result = await db.execute(
                select(
                    func.count(Message.id).label("total_messages"),
                    func.coalesce(func.sum(Message.tokens), 0).label("total_tokens"),
                    func.coalesce(func.sum(Message.latency_ms), 0).label("total_latency_ms"),
                    func.count(Message.conversation_id.distinct()).label("active_sessions"),
                )
            )
            row = result.one()
            total_messages = int(row.total_messages or 0)
            total_tokens = int(row.total_tokens or 0)
            total_latency = int(row.total_latency_ms or 0)
            active_sessions = int(row.active_sessions or 0)
            assistant_msgs = total_messages // 2  # 粗略估算 assistant 消息数
            return {
                "db_total_messages": total_messages,
                "db_total_tokens": total_tokens,
                "db_total_latency_ms": total_latency,
                "db_active_sessions": active_sessions,
                "db_avg_latency_ms": round(total_latency / max(assistant_msgs, 1), 1),
                "db_est_cost": estimate_cost(total_tokens // 2, total_tokens // 2),
                "note": "从 PG messages 表统计，永久保存；与进程内存累计互补。",
            }
    except Exception as e:
        return {"error": str(e), "note": "DB 指标读取失败（表可能未创建），使用进程内存累计。"}