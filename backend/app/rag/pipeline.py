# 作者：zcy
"""RAG 检索管道（参考 Dify IndexingRunner 的 Extract→Transform→Load 三段式设计）。

把分散的检索步骤封装为统一管道，面试时可清晰展示"数据从哪来→怎么处理→怎么用"。

管道阶段：
1. **Extract（提取）**：从 pgvector 向量库 + 关键词数据源提取原始候选
   - 语义召回：需求 embedding → pgvector 余弦 TopK
   - 关键词召回：按区域/价格/户型硬过滤
2. **Transform（转换）**：合并去重 → gte-rerank 重排 → 截断 TopK
   - 合并：关键词 ∪ 语义（并集去重）
   - 重排：gte-rerank 对候选按相关性打分排序（失败自动跳过）
3. **Load（加载）**：返回结构化 Listing 列表给 Agent 使用

与 Dify 的对应：
- Dify IndexingRunner：文档解析→分段→向量化→入库（入库管道）
- 本项目 RetrievalPipeline：需求向量化→多路召回→重排→输出（检索管道）
- 两者都是"输入→多阶段处理→输出"的管道模式，每阶段独立可替换
"""
from __future__ import annotations

from app.models.schemas import Listing, RentRequirement
from app.rag.hybrid_retriever import hybrid_search, semantic_recall
from app.tools.listing_source import get_sources


class RetrievalPipeline:
    """统一检索管道：Extract → Transform → Load。

    用法：
        pipeline = RetrievalPipeline()
        listings = await pipeline.run(req, top_k=20)
    """

    def __init__(self, enable_semantic: bool = True, enable_rerank: bool = True):
        self.enable_semantic = enable_semantic
        self.enable_rerank = enable_rerank

    async def run(self, req: RentRequirement, top_k: int = 20) -> list[Listing]:
        """执行完整检索管道。"""
        # Stage 1: Extract — 多路召回（关键词 + 语义）
        # Stage 2: Transform — 合并去重 + rerank
        # Stage 3: Load — 截断 TopK 后返回
        items = await hybrid_search(req, use_semantic=self.enable_semantic, use_rerank=self.enable_rerank)
        return items[:top_k]

    async def extract_semantic(self, req: RentRequirement) -> list[Listing]:
        """Extract 阶段：语义召回（pgvector 余弦相似度）。独立可调用，便于调试/评测。"""
        return await semantic_recall(req)

    def extract_keyword(self, req: RentRequirement) -> list[Listing]:
        """Extract 阶段：关键词召回（硬条件过滤）。独立可调用，便于调试/评测。"""
        out: list[Listing] = []
        for src in get_sources():
            out.extend(src.search(req))
        return out
