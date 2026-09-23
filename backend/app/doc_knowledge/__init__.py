# 作者：zcy
"""多模态文档知识库：PDF/PPT/Excel 等文档的解析、切块、入库与检索。

与房源 RAG（listings）共用 pgvector + 百炼 embedding，新增 doc_chunks 表，
检索返回带引用（来源文档/页码）的原文块，防幻觉。
"""
