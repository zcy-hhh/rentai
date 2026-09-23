// 作者：zcy
// 与后端 app/models/schemas.py 对齐的 API 类型

export interface RentRequirement {
  district?: string | null;
  max_price: number;
  min_area?: number | null;
  room_types?: string[];
  commute_to?: string | null;
  commute_max_minutes?: number | null;
  tags?: string[];
  user_note?: string | null;
}

export interface RiskNote {
  kind: string;
  level: "high" | "medium" | "low";
  detail: string;
  reference: string;
}

export interface Listing {
  id: string;
  title: string;
  source: string;
  url?: string;
  district: string;
  address?: string;
  price: number;
  area: number;
  room_type: string;
  orientation?: string;
  floor?: string;
  facilities?: string[];
  listing_date?: string;
  is_verified: boolean;
  risk_flags?: string[];
  description?: string;
}

export interface CandidateListing extends Listing {
  match_score: number;
  match_reasons: string[];
  risks: RiskNote[];
  commute_minutes?: number | null;
}

export interface ViewingList {
  list_id: string;
  requirement: RentRequirement;
  candidates: CandidateListing[];
  verify_items: string[];
  ask_items: string[];
  status: string;
}

export interface RentResponse {
  requirement: RentRequirement;
  total_matched: number;
  candidates: CandidateListing[];
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
  tenant: string;
}

// 看房清单生成后的流程事件（SSE 节点名）
export type FlowNode = "retrieve" | "filter" | "rank" | "risk_check" | "build_list";

// ReAct Agent 的模型自主工具调用轨迹（对应后端 app/agents/react_agent.py 的 trace 项）
export interface AgentToolCall {
  tool: string;
  args: Record<string, unknown>;
  thought: string;
}

// C 端展示用的通俗步骤文案（对普通租房用户隐藏工具名/技术词）
export const AGENT_TOOL_LABELS: Record<string, string> = {
  search_listings: "搜索房源",
  filter_hard: "按你的要求筛选",
  score_rank: "帮你排序",
  check_risks: "排查房源风险",
  build_viewing_list: "生成看房清单",
  amap_geocode: "定位房源位置",
  amap_poi_around: "查看周边配套",
  amap_commute: "估算通勤时间",
};

// 对话式 Agent 单轮返回（对应后端 app/agents/conversational.py 的 chat_step）
export type ChatStepKind = "clarify" | "message" | "result" | "escalate" | "error";
export interface ReflexionLog {
  round: number;
  issues: string[];
  improvement: string;
}
export interface Escalation {
  reason: string[];
  context: string;
  advice: string;
}
export interface AgentUsage {
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  retry_rounds: number;
  est_cost: number;
  note: string;
}
export interface ChatStepResult {
  kind: ChatStepKind;
  text?: string;
  session_id?: string;
  requirement?: RentRequirement;
  trace?: AgentToolCall[];
  reflexion?: ReflexionLog[];
  escalation?: Escalation;
  usage?: AgentUsage;
  viewing?: ViewingList | null;
}

