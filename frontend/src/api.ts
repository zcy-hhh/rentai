// 作者：zcy
// 与后端 app/models/schemas.py 对齐的 API 类型
import type {
  AgentToolCall,
  ChatStepResult,
  LoginRequest,
  LoginResponse,
  RentRequirement,
  RentResponse,
  ViewingList,
} from "./types";

const BASE = "/api";

// 登录
export async function apiLogin(body: LoginRequest): Promise<LoginResponse> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new Error(e.detail?.[0]?.msg ?? e.detail ?? "登录失败");
  }
  return res.json();
}

// 智能检索（一次性返回）
export async function apiSearch(
  req: RentRequirement,
  token?: string,
): Promise<RentResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/rent/search`, {
    method: "POST",
    headers,
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("检索失败，请检查输入");
  return res.json();
}

// 生成看房清单（一次性）
export async function apiCreateViewingList(
  req: RentRequirement,
  token?: string,
): Promise<ViewingList> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/rent/viewing-list`, {
    method: "POST",
    headers,
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("生成看房清单失败");
  return res.json();
}

// 确认/调整看房清单（持久化 + 并入用户偏好）
export async function apiConfirm(
  listId: string,
  action: "confirm" | "adjust",
  note: string,
): Promise<ViewingList> {
  const res = await fetch(`${BASE}/rent/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ list_id: listId, action, note, user_id: "demo" }),
  });
  if (!res.ok) throw new Error("操作失败");
  return res.json();
}

// 按 id 读取已生成的看房清单（复用/二次查看，刷新或重进不丢）
export async function apiGetViewing(listId: string): Promise<ViewingList> {
  const res = await fetch(`${BASE}/rent/viewing/${listId}`);
  if (!res.ok) throw new Error("看房清单不存在");
  return res.json();
}

// SSE 解析：把响应体逐事件回调，返回 build_list 携带的清单（若走到）
async function consumeSSE<T>(res: Response, onEvent: (event: string, payload: unknown) => void): Promise<T | null> {
  if (!res.ok || !res.body) throw new Error("流式连接失败");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: T | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "error") throw new Error(payload.error ?? "执行中断");
      onEvent(event, payload);
      if (event === "build_list") final = payload as unknown as T;
    }
  }
  return final;
}

// SSE 流式检索（确定性管道）：逐步回调各节点事件
export async function apiSearchStream(
  req: RentRequirement,
  onEvent: (node: string, payload: unknown) => void,
  token?: string,
): Promise<ViewingList | null> {
  const res = await fetch(`${BASE}/rent/search/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(req),
  });
  return consumeSSE<ViewingList>(res, onEvent);
}

// ReAct Agent 流式检索：模型自主调工具，逐步回调 tool_call 轨迹，返回清单
export async function apiAgentSearchStream(
  req: RentRequirement,
  onToolCall: (tc: AgentToolCall) => void,
  token?: string,
): Promise<ViewingList | null> {
  const res = await fetch(`${BASE}/rent/agent/search/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(req),
  });
  return consumeSSE<ViewingList>(res, (event, payload) => {
    if (event === "tool_call") onToolCall(payload as AgentToolCall);
  });
}

// 对话式 Agent：自然语言多轮（意图解析 + 澄清 + 执行）
// history：前端携带的完整对话历史（[(role, content), ...]），作上下文真相源（后端 Redis 记忆可能过期）
export async function apiChat(
  message: string,
  sessionId: string,
  history: [string, string][] = [],
): Promise<ChatStepResult> {
  const res = await fetch(`${BASE}/rent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, history }),
  });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new Error(e.detail ?? "对话请求失败");
  }
  return res.json();
}

// ---------- 租房知识库（多模态文档：PDF/PPT/Excel） ----------
export interface DocHit {
  text: string;
  source_name: string;
  page: number;
  sheet?: string | null;
  score: number;
}
export interface DocSearchResult {
  query: string;
  count: number;
  hits: DocHit[];
}

// 上传文档入库
export async function apiDocIngest(
  file: File,
  onReady: (chunks: number) => void,
): Promise<void> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/rent/doc/ingest`, { method: "POST", body: fd });
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new Error(e.detail ?? "文档解析失败");
  }
  const d = await res.json();
  onReady(d.chunks ?? 0);
}

// 检索知识库（带引用）
export async function apiDocSearch(q: string, topK = 5): Promise<DocSearchResult> {
  const res = await fetch(`${BASE}/rent/doc/search?q=${encodeURIComponent(q)}&top_k=${topK}`);
  if (!res.ok) throw new Error("检索失败");
  return res.json();
}

// ---------- 观测后台：评测指标 + 可观测统计 + 数据基线 ----------
export interface ObserveMetric {
  match_cases: number;
  "match_precision@k": number;
  match_recall: number;
  risk_cases: number;
  risk_recall: number;
}
export interface ObserveDecisionCase {
  name: string;
  trace: string[];
  score: number;
  criteria: { name: string; pass: boolean }[];
}
export interface ObserveUsage {
  chat_turns: number;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  est_cost: number;
  retry_rounds: number;
  avg_latency_ms: number;
}
export interface ObserveSummary {
  metrics: ObserveMetric;
  decision: { avg_decision_score: number; cases: ObserveDecisionCase[] };
  usage: ObserveUsage;
  data: { listings: number; viewings: number; doc_chunks: number };
}

// 观测后台：评测指标 + 可观测 + 数据基线
export async function apiObserveMetrics(): Promise<ObserveSummary> {
  const res = await fetch(`${BASE}/rent/observe/metrics`);
  if (!res.ok) throw new Error("获取观测指标失败");
  return res.json();
}

// 观测后台：Ragas 语义评测（慢，调 LLM，前端按钮触发）
export async function apiObserveRagas(limit = 3): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/rent/observe/ragas?limit=${limit}`);
  if (!res.ok) throw new Error("语义评测失败");
  return res.json();
}

