<p align="center">
  <h1 align="center">🏠 RentAI</h1>
  <p align="center">AI Agent 驱动的智能租房助手 —— 把「翻平台 + 手动比价 + 怕被坑」压缩成一次自然语言输入、一份可执行的看房清单</p>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.12-blue" alt="Python"/>
    <img src="https://img.shields.io/badge/FastAPI-0.141-green" alt="FastAPI"/>
    <img src="https://img.shields.io/badge/LangGraph%2FLangChain-blue" alt="LangGraph"/>
    <img src="https://img.shields.io/badge/React-18-61dafb" alt="React"/>
    <img src="https://img.shields.io/badge/PostgreSQL%2Bpgvector-336791" alt="PostgreSQL"/>
    <img src="https://img.shields.io/badge/Redis-7-dc382d" alt="Redis"/>
    <img src="https://img.shields.io/badge/Docker-Compose-2496ed" alt="Docker"/>
    <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License"/>
  </p>
</p>

> **企业级工程标准**的 C 端生活化 AI Agent 项目。生活场景有共鸣，工程硬度有区分度——确定性管道与模型自主决策双轨、Harness 治理、评测体系与独立观测后台、多租户 / 鉴权 / 审计 / 可部署。

---

## ✨ 特性

- **🗣️ 单一对话主页面**：所有操作收敛到一个自然语言对话框——AI 自主判断是闲聊、澄清追问还是执行找房，无需用户在多个页面间切换
- **🤖 AI 自主模式路由**：模型通过 function calling 自主选择执行模式——需求明确走确定性管道（快速稳定），需求复杂走 ReAct 自主决策（灵活+反思自纠错）
- **🧠 多轮记忆持久化**：短期会话历史 + 长期用户画像，Redis 持久化带 TTL；前端历史为上下文真相源，新增需求做增量执行而非重复生成
- **📋 看房清单主动生成**：对话返回候选房源后，用户一键「保存为看房清单」，PG 持久化，支持确认/调整闭环，确认结果并入用户画像
- **🛡️ Harness 治理层**：输入越界护栏、死循环护栏、候选截断防上下文膨胀、引用约束防幻觉、人工兜底升级
- **🔍 混合检索 RAG + pgvector**：关键词 ∪ 语义召回 → gte-rerank 重排；多平台房源可插拔
- **📚 多模态文档知识库**：上传 PDF / PPT / Excel 解析入库，检索带来源/页码引用
- **📊 评测体系 + 观测后台**：确定性匹配指标 + Agent 决策质量 + Ragas 语义指标；独立观测台实时看对话用量与数据基线，8 秒自动刷新
- **🔐 企业级工程**：JWT + RBAC + 多租户隔离、MCP 工具暴露、SSE 流式、Docker Compose 一键部署

---

## 🏗️ 架构总览

![RentAI 架构图](docs/architecture.svg)

**核心设计**：所有交互收敛到单一对话主页面——AI 每轮做意图解析，自主决定是闲聊回复、澄清追问还是执行找房；执行时模型自主选择「确定性管道」（LangGraph 五节点，快速稳定可复现）或「ReAct 自主决策」（function calling 灵活组合工具 + 反思自纠错）。候选房源放在共享上下文，工具只返回摘要给模型观察，模型负责决策、确定性函数负责执行。

---

## 🧰 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · Uvicorn |
| Agent 编排 | LangGraph StateGraph · LangChain ReAct · Harness |
| LLM | 阿里云百炼：qwen-plus / text-embedding-v4 / gte-rerank |
| RAG | 混合检索 → 重排 · 多模态文档知识库 |
| 存储 | PostgreSQL + pgvector · Redis · MinIO |
| 协议 | MCP · Function Calling · SSE |
| 前端 | React 18 · Vite 6 · TypeScript · Zustand · Tailwind · react-router |
| 工程 | Docker Compose · pytest · JWT/RBAC · Alembic 迁移 · 观测后台 |

---

## 🚀 快速开始

### 1. 克隆 & 配置密钥

```bash
git clone <your-repo-url> rentai && cd rentai
cp backend/.env.example backend/.env   # 填入你自己的密钥
```

`backend/.env` 需配置，示例见 `backend/.env.example`：

```ini
# 阿里云百炼
DASHSCOPE_API_KEY=sk-你的百炼APIKey
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v4
RERANK_MODEL=gte-rerank
# 高德开放平台
AMAP_KEY=你的高德Web服务Key
```

> 🔒 所有密钥仅存于 `backend/.env`，已被 `.gitignore` 排除，**不会提交到仓库**。

### 2. 一键启动

```bash
docker compose up -d
# 前端: http://localhost:5173   后端 API: http://localhost:8000
```

三个容器自动就绪：`rentai-postgres`(pgvector) + `rentai-redis` + `rentai-backend`。

### 3. 本地开发

```bash
# 后端
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
# 前端
cd frontend && npm install && npm run dev
```

---

## 🧪 评测与观测

| 层次 | 对象 | 指标 |
|---|---|---|
| ① 结果质量 | 检索→过滤→排序→避坑→清单管道 | match_precision@k / match_recall / risk_recall |
| ② Agent 决策质量 | ReAct 自主调工具轨迹 | avg_decision_score |
| ③ 语义指标 | RAG 答案质量 | faithfulness / context_precision |
| ④ 机制自检 | 评测脚本本身 | 指标区间 + 同源自洽 = 1.0 |

独立观测后台：确定性评测 + 对话用量 + 数据基线，实时自动刷新。

```bash
curl http://localhost:8000/api/rent/observe/metrics
curl "http://localhost:8000/api/rent/observe/ragas?limit=3"   # 语义评测
```

---

## 📁 目录结构

```
rentai/
├─ backend/
│  ├─ app/
│  │  ├─ api/            # REST/SSE 路由 + JWT/RBAC + 看房清单保存端点
│  │  ├─ agents/         # 对话式Agent(意图解析+模式路由) / LangGraph管道 / ReAct / 反思
│  │  ├─ rag/            # 混合检索 + pgvector
│  │  ├─ doc_knowledge/  # 多模态文档知识库(PDF/PPT/Excel)
│  │  ├─ tools/          # 数据源 / 通勤 / ReAct工具 / MCP
│  │  ├─ llm/            # 百炼网关 / embedding / rerank
│  │  ├─ core/           # 配置 / Harness护栏 / 鉴权
│  │  ├─ services/       # 看房清单持久化 + HITL
│  │  └─ observability.py # 请求级指标收集(对话轮次/token/延迟/成本)
│  ├─ evals/             # 评测脚本(确定性+Agent决策+Ragas)
│  └─ alembic/           # 数据库迁移
├─ frontend/src/
│  ├─ pages/             # Chat(单一主页面) / Viewing / Knowledge / Observe
│  ├─ components/        # Layout / 候选房源卡片 / 保存清单按钮
│  ├─ store/             # Zustand 状态管理
│  └─ api.ts             # 后端API封装
├─ docs/
│  ├─ architecture.svg   # 架构图(分层卡片式)
│  └─ 部署文档.md         # Docker Compose 部署指南
└─ docker-compose.yml    # postgres(pgvector) + redis + backend 一键部署
```

---

## 📚 文档

- [`docs/部署文档.md`](docs/部署文档.md)：Docker Compose 一键部署、密钥配置、常用命令与 FAQ

---

## 📝 License

[MIT](LICENSE) —— 仅供学习交流使用。
