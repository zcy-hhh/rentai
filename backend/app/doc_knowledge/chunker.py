# 作者：zcy
"""文本切块：固定窗口 + 重叠，优先在句号/换行处断开。

中文按字数切，保留相邻块 10% 左右重叠以缓解跨块语义割裂；
每块记录所在页码（粗略取块头所在页）+ 全局块号 + 来源元数据。
"""
from __future__ import annotations

DEFAULT_CHUNK_SIZE = 220
DEFAULT_OVERLAP = 30


def chunk_document(
    pages: list[dict],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[dict]:
    chunks: list[dict] = []
    buf = ""
    buf_page = 1
    for pg in pages:
        buf += (pg.get("text") or "") + "\n"
        buf_page = pg["page"]
        while len(buf) >= chunk_size:
            cut = chunk_size
            # 优先在句号/换行处断，避免切碎语义
            idx = max(buf.rfind("。", 0, cut), buf.rfind("\n", 0, cut))
            if idx > chunk_size * 0.5:
                cut = idx + 1
            piece = buf[:cut].strip()
            if piece:
                chunks.append(
                    {
                        "text": piece,
                        "page": buf_page,
                        "chunk_index": len(chunks),
                        "sheet": pg.get("sheet"),
                    }
                )
            buf = buf[cut - overlap :]
            buf_page = pg["page"]
    tail = buf.strip()
    if tail:
        chunks.append(
            {
                "text": tail,
                "page": buf_page,
                "chunk_index": len(chunks),
                "sheet": pages[-1].get("sheet") if pages else None,
            }
        )
    return chunks
