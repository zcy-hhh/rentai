# 作者：zcy
"""Agent 用 LLM：基于 langchain ChatOpenAI 指向阿里云百炼。

create_react_agent 需要能 bind_tools 的 ChatModel；现有 `llm.client.chat`
是直接调 AsyncOpenAI，无法 bind 工具，故这里用 langchain-openai 封装，
指向同一套 settings（qwen-plus，OpenAI 兼容 base_url）。
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import settings


def build_agent_llm() -> ChatOpenAI:
    """构建支持 function calling 的对话模型（qwen-plus）。"""
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=0.3,
        max_tokens=2048,
    )
