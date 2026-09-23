# 作者：zcy
"""REST API 路由。"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.graph import rent_graph
from app.core.harness import (
    AgentStepLimitError,
    ContextGuardError,
    HarnessError,
    guard_requirement,
    safe_stream,
)
from app.models.schemas import CandidateListing, ChatRequest, ConfirmRequest, RentRequirement, RentResponse, ViewingList
from app.services.viewing import pg_viewing_store

# Pydantic model -> JSON 可序列化结构（避免 default=str 把对象降级成 repr 字符串）
def _jsonable(o):
    if hasattr(o, "model_dump"):  # Pydantic v2 model（Listing / CandidateListing / ViewingList…）
        return o.model_dump(mode="json")
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o

router = APIRouter(prefix="/rent", tags=["rent"])


@router.post("/search", response_model=RentResponse, summary="智能租房检索")
def search(req: RentRequirement) -> RentResponse:
    """输入租房需求，运行 Agent 编排，返回排序后的候选房源清单。"""
    try:
        guard_requirement(req)  # Harness 上下文护栏：输入越界先拦截
    except HarnessError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result = rent_graph.invoke({"requirement": req})
    return RentResponse(
        requirement=req,
        total_matched=len(result["ranked"]),
        candidates=result["ranked"],
    )


@router.post("/search/stream", summary="智能租房检索（SSE 流式）")
async def search_stream(req: RentRequirement) -> StreamingResponse:
    """SSE 流式返回 Agent 逐步执行过程：检索→筛选→排序→避坑→清单。

    前端可边执行边展示每个环节的中间结果（检索到 N 条 → 过滤剩 M 条 → …）。
    """
    try:
        guard_requirement(req)  # Harness 上下文护栏
    except HarnessError as e:
        raise HTTPException(status_code=422, detail=str(e))

    async def gen():
        # SSE 注释行（保活）
        yield ": connected\n\n"
        try:
            async for event in safe_stream(req):
                for node, payload in event.items():
                    data = json.dumps(_jsonable(payload), ensure_ascii=False)
                    yield f"event: {node}\ndata: {data}\n\n"
        except AgentStepLimitError as e:  # Harness 死循环护栏
            data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"
        except Exception as e:  # 兜底：流中断不挂死
            data = json.dumps({"error": f"执行中断：{e}"}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agent/search/stream", summary="ReAct Agent 检索（SSE·模型自主调工具）")
async def agent_search_stream(req: RentRequirement) -> StreamingResponse:
    """真正的 Agent 主路径：LLM 通过 function calling 自主决定调用哪些工具。

    SSE 流式返回每次"模型调用工具"的轨迹（tool + 参数 + 思考），
    最后 build_list 事件携带生成的看房清单。模型自主决策，非固定管道。
    """
    try:
        guard_requirement(req)  # Harness 上下文护栏
    except HarnessError as e:
        raise HTTPException(status_code=422, detail=str(e))

    from app.agents.react_agent import run_react

    async def gen():
        yield ": connected\n\n"
        try:
            trace, vl = await run_react(req)
            for i, t in enumerate(trace):
                data = json.dumps(_jsonable(t), ensure_ascii=False)
                yield f"event: tool_call\ndata: {data}\n\n"
            if vl:
                data = json.dumps(_jsonable(vl), ensure_ascii=False)
                yield f"event: build_list\ndata: {data}\n\n"
            else:
                data = json.dumps({"error": "Agent 未收敛产出清单"}, ensure_ascii=False)
                yield f"event: error\ndata: {data}\n\n"
        except Exception as e:  # Agent 异常兜底（不挂死，可降级）
            data = json.dumps({"error": f"Agent 执行中断：{e}"}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


class SaveViewingRequest(BaseModel):
    """对话结果保存为看房清单：用户主动点击，而非 Agent 自动生成。"""
    requirement: RentRequirement
    candidates: list[CandidateListing]
    verify_items: list[str] = []
    ask_items: list[str] = []


@router.post("/viewing/save", response_model=ViewingList, summary="保存对话结果为看房清单")
async def save_viewing(body: SaveViewingRequest) -> ViewingList:
    """用户在对话结果里主动点击"保存为看房清单"，把当前推荐房源持久化到 PostgreSQL。"""
    vl = ViewingList(
        list_id=uuid.uuid4().hex[:12],
        requirement=body.requirement,
        candidates=body.candidates,
        verify_items=body.verify_items,
        ask_items=body.ask_items,
        status="pending",
    )
    return await pg_viewing_store.save(vl, user_id="demo")


@router.post("/viewing-list", response_model=ViewingList, summary="生成看房清单（人工确认）")
async def create_viewing_list(req: RentRequirement) -> ViewingList:
    """运行完整 Agent 编排，生成带避坑标注的看房清单，持久化到 PostgreSQL（重启不丢）。"""
    try:
        guard_requirement(req)  # Harness 上下文护栏
    except HarnessError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result = rent_graph.invoke({"requirement": req})
    vl = result["viewing_list"]
    # PG 持久化（M6 建表、M13 接入）——user_id 后续接 JWT 鉴权注入
    return await pg_viewing_store.save(vl, user_id="demo")


@router.post("/confirm", response_model=ViewingList, summary="确认/调整看房清单（人工闭环）")
async def confirm_viewing_list(body: ConfirmRequest) -> ViewingList:
    """用户确认或调整看房清单，操作审计留痕，并把认可/调整过的需求并入长期画像。"""
    vl = await pg_viewing_store.confirm(body.list_id, body.action, body.note)
    if vl is None:
        raise HTTPException(status_code=404, detail=f"看房清单 {body.list_id} 不存在")
    # 实际作用：确认/调整后，把该需求并入用户画像，后续 Agent 找房会参考（不是"确认完就废弃"）
    from app.agents.conversational import record_user_preference

    await record_user_preference(body.user_id or "demo", vl.requirement)
    return vl


@router.get("/viewing/{list_id}", response_model=ViewingList, summary="按 id 读取看房清单（复用）")
async def get_viewing_list(list_id: str) -> ViewingList:
    """从 PostgreSQL 按 list_id 读回已生成的看房清单，供复用/二次查看（刷新或重进不丢）。"""
    vl = await pg_viewing_store.get(list_id)
    if vl is None:
        raise HTTPException(status_code=404, detail=f"看房清单 {list_id} 不存在")
    return vl


@router.post("/chat", summary="对话式 Agent（多轮意图解析 + 澄清 + 执行）")
async def chat(body: ChatRequest) -> dict:
    """对话式 Agent 主入口：自然语言多轮。

    意图理解模块从"对话历史 + 用户画像 + 当前消息"推断需求：
    - 信息不足 → 返回 kind=clarify（追问一个关键信息）
    - 需求齐全 → 返回 kind=result（复用 ReAct 执行，含工具轨迹 + 带链接房源清单）
    - 闲聊 → 返回 kind=message
    短期记忆按 session_id 累积，长期画像按 user_id 累积。
    """
    from app.agents.conversational import chat_step

    try:
        # history 由前端携带（完整对话），作为上下文真相源；缺省时后端回退 Redis 会话记忆
        return await chat_step(body.user_id, body.session_id, body.message, history=body.history)
    except Exception as e:  # 对话兜底（不挂死）
        return {"kind": "error", "text": f"对话处理失败：{e}"}


@router.post("/doc/ingest", summary="多模态文档入库（PDF/PPT/Excel）")
async def doc_ingest(file: UploadFile = File(...), doc_id: str | None = None) -> dict:
    """上传文档解析→切块→向量化→写入 doc_chunks（pgvector）。支持 PDF/PPT/Excel/文本。"""
    from app.doc_knowledge.ingest import ingest_document

    suffix = Path(file.filename or "doc").suffix
    tmp_path = tempfile.mktemp(suffix=suffix)
    tmp_path = tmp_path or tempfile.mktemp(suffix=suffix)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        return await ingest_document(tmp_path, file.filename or "doc", doc_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"文档入库失败：{e}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.get("/doc/search", summary="文档知识库检索（带引用）")
async def doc_search(q: str, top_k: int = 5) -> dict:
    """按 query 从文档知识库检索，返回带来源/页码引用的原文块。"""
    from app.doc_knowledge.retriever import search_docs

    hits = await search_docs(q, top_k)
    return {"query": q, "hits": hits, "count": len(hits)}


# ---------- 观测后台：评测指标 + 可观测统计 + 数据基线 ----------
@router.get("/observe/metrics", summary="观测后台：确定性/决策评测 + 可观测 + 数据基线")
async def observe_metrics() -> dict:
    """一次返回观测后台所需指标（确定性匹配/避坑 + Agent 决策 + 对话用量 + 数据规模）。"""
    from evals.run import run_eval
    from evals.eval_agent_decisions import evaluate_agent_decisions
    from app.observability import snapshot_metrics
    from app.db.session import SessionLocal
    from sqlalchemy import text as _text

    counts = {"listings": 0, "viewings": 0, "doc_chunks": 0}
    try:
        async with SessionLocal() as s:
            for table, key in (("listings", "listings"), ("viewings", "viewings"), ("doc_chunks", "doc_chunks")):
                r = await s.execute(_text(f"SELECT count(*) FROM {table}"))
                counts[key] = int(r.scalar() or 0)
    except Exception:
        pass  # DB 不可用时只返回内存指标，不阻塞观测页

    return {
        "metrics": run_eval(),
        "decision": evaluate_agent_decisions(),
        "usage": snapshot_metrics(),
        "data": counts,
    }


@router.get("/observe/ragas", summary="观测后台：Ragas 语义评测（慢，调 LLM，独立子进程避免 uvloop 冲突）")
async def observe_ragas(limit: int = 3) -> dict:
    """跑 ragas 语义指标（faithfulness / context_precision / response_relevancy）。

    ragas 在模块级执行 nest_asyncio.apply()，无法在 uvicorn 的 uvloop 事件循环上运行，
    故放到独立子进程（标准 asyncio loop）执行，规避冲突。慢（调 qwen），由前端按钮触发。
    """
    import asyncio
    import json as _json
    import os as _os
    import subprocess as _sp
    import sys as _sys

    def _run() -> dict:
        code = (
            "import sys,json;"
            "sys.path.insert(0,'/app');"
            "from evals.ragas_eval import run_ragas_eval;"
            "print(json.dumps(run_ragas_eval(%d)))" % limit
        )
        p = _sp.run(
            [_sys.executable, "-c", code],
            capture_output=True, text=True, cwd="/app", env=_os.environ.copy(), timeout=300,
        )
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout)[-2000:])
        lines = [l for l in p.stdout.strip().splitlines() if l.strip().startswith("{")]
        return _json.loads(lines[-1])

    return await asyncio.get_event_loop().run_in_executor(None, _run)

