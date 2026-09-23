# 作者：zcy
"""百炼 DashScope API 连通性验证（轻量：各 1 次调用，控制用量）。"""
from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

load_dotenv("E:/Code/rentai/backend/.env")
key = os.getenv("DASHSCOPE_API_KEY", "")
base = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
headers = {"Authorization": f"Bearer {key}"}
out: list[str] = []

# 1) chat 连通性（用最便宜的 qwen-turbo，极短输入）
r = httpx.post(
    f"{base}/chat/completions",
    headers=headers,
    json={"model": "qwen-turbo", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
    timeout=30,
)
if r.status_code == 200:
    out.append(f"chat OK: {r.json()['choices'][0]['message']['content']!r}")
else:
    out.append(f"chat FAIL {r.status_code}: {r.text[:300]}")

# 2) embedding 连通性（text-embedding-v4）
r2 = httpx.post(
    f"{base}/embeddings",
    headers=headers,
    json={"model": "text-embedding-v4", "input": "测试"},
    timeout=30,
)
if r2.status_code == 200:
    dim = len(r2.json()["data"][0]["embedding"])
    out.append(f"embedding OK, dim={dim}")
else:
    out.append(f"embedding FAIL {r2.status_code}: {r2.text[:300]}")

print("\n".join(out))
