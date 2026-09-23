// 作者：zcy
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  apiAgentSearchStream,
  apiCreateViewingList,
  apiSearchStream,
} from "../api";
import { useAuth } from "../store/auth";
import { useFavorites } from "../store/favorites";
import { useHistory } from "../store/history";
import type {
  AgentToolCall,
  CandidateListing,
  FlowNode,
  RentRequirement,
  ViewingList,
} from "../types";
import { AGENT_TOOL_LABELS } from "../types";

type Mode = "pipeline" | "agent";
type SortKey = "score" | "price_asc" | "price_desc" | "area_desc";

interface FlowStep {
  node: FlowNode;
  label: string;
  count: number;
  status: "pending" | "running" | "done";
}

interface TraceItem {
  name: string;
  status: "pending" | "running" | "done";
  thought?: string;
}

const FLOW_LABELS: Record<FlowNode, string> = {
  retrieve: "搜索房源",
  filter: "按你的要求筛选",
  rank: "为你排序",
  risk_check: "排查风险",
  build_list: "生成看房清单",
};

const PRICE_QUICK = [1500, 2000, 3000, 5000];
const ROOM_OPTIONS = ["1室", "2室", "3室"];
const DISTRICT_QUICK = ["新吴区", "滨湖区", "梁溪区", "锡山区"];

// 最近一次清单持久化到 localStorage，回主页/刷新仍可复用进入
const LAST_VIEWING_KEY = "rentai:last_viewing";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

type QueueItem =
  | { kind: "step"; node: string }
  | { kind: "tool"; name: string };

export default function Search() {
  const token = useAuth((s) => s.token);
  const navigate = useNavigate();

  const [district, setDistrict] = useState("");
  const [maxPrice, setMaxPrice] = useState("3000");
  const [minArea, setMinArea] = useState("");
  const [roomType, setRoomType] = useState("1室");
  const [commuteTo, setCommuteTo] = useState("");
  const [tags, setTags] = useState("");
  const [userNote, setUserNote] = useState("");

  const [mode, setMode] = useState<Mode>("pipeline");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [steps, setSteps] = useState<FlowStep[]>([]);
  const [traces, setTraces] = useState<TraceItem[]>([]);
  const [candidates, setCandidates] = useState<CandidateListing[]>([]);
  const [viewingList, setViewingList] = useState<ViewingList | null>(null);
  // 最近一次清单：localStorage 持久化，回主页/刷新仍有入口复用
  const [lastViewing, setLastViewing] = useState<{ list_id: string; status: string } | null>(() => {
    try {
      const raw = localStorage.getItem(LAST_VIEWING_KEY);
      return raw ? (JSON.parse(raw) as { list_id: string; status: string }) : null;
    } catch {
      return null;
    }
  });
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const favorites = useFavorites();
  const history = useHistory();

  // 统一播放队列：事件可能瞬间全到，这里逐个播放"执行中→完成"，节奏可感知
  const queue = useRef<QueueItem[]>([]);
  const pumping = useRef(false);
  const countsRef = useRef<Record<string, number>>({});
  const vlRef = useRef<ViewingList | null>(null);

  function pump() {
    if (pumping.current) return;
    pumping.current = true;
    void (async () => {
      while (true) {
        const item = queue.current.shift();
        if (!item) {
          pumping.current = false;
          return;
        }
        if (item.kind === "step") {
          setSteps((prev) =>
            prev.map((s) => (s.node === item.node ? { ...s, status: "running" } : s)),
          );
          await sleep(650);
          const count = countsRef.current[item.node] ?? 0;
          setSteps((prev) =>
            prev.map((s) => (s.node === item.node ? { ...s, status: "done", count } : s)),
          );
        } else {
          setTraces((prev) =>
            prev.map((t) => (t.name === item.name ? { ...t, status: "running" } : t)),
          );
          await sleep(650);
          setTraces((prev) =>
            prev.map((t) => (t.name === item.name ? { ...t, status: "done" } : t)),
          );
        }
        if ((item.kind === "step" && item.node === "build_list") ||
            (item.kind === "tool" && item.name === "build_viewing_list")) {
          if (vlRef.current) {
            setViewingList(vlRef.current);
            setCandidates(vlRef.current.candidates);
          }
        }
        await sleep(120);
      }
    })();
  }

  function buildReq(): RentRequirement {
    return {
      district: district || null,
      max_price: Number(maxPrice) || 3000,
      min_area: minArea ? Number(minArea) : null,
      room_types: [roomType],
      commute_to: commuteTo || null,
      tags: tags ? tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean) : [],
      user_note: userNote || null,
    };
  }

  function applyReq(r: RentRequirement) {
    setDistrict(r.district ?? "");
    setMaxPrice(String(r.max_price ?? 3000));
    setMinArea(r.min_area ? String(r.min_area) : "");
    setRoomType(r.room_types?.[0] ?? "1室");
    setCommuteTo(r.commute_to ?? "");
    setTags(r.tags?.join(", ") ?? "");
  }

  async function onSearch() {
    const req = buildReq();
    setLoading(true);
    setError("");
    setCandidates([]);
    setViewingList(null);
    queue.current = [];
    pumping.current = false;
    countsRef.current = {};
    vlRef.current = null;
    history.add(req);

    if (mode === "pipeline") {
      setTraces([]);
      setSteps(
        (Object.keys(FLOW_LABELS) as FlowNode[]).map((node) => ({
          node,
          label: FLOW_LABELS[node],
          count: 0,
          status: "pending",
        })),
      );
      try {
        await apiSearchStream(
          req,
          (node, payload) => {
            let count = 0;
            if (node === "build_list") {
              vlRef.current = (payload as { viewing_list: ViewingList }).viewing_list;
              count = vlRef.current.candidates.length;
            } else {
              const rec = payload as { raw?: unknown[]; filtered?: unknown[]; ranked?: unknown[] };
              count = rec.ranked?.length ?? rec.filtered?.length ?? rec.raw?.length ?? 0;
            }
            countsRef.current[node] = count;
            queue.current.push({ kind: "step", node });
            pump();
          },
          token ?? undefined,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "找房失败");
      } finally {
        setLoading(false);
      }
      return;
    }

    // agent 模式
    setSteps([]);
    setTraces([]);
    try {
      const finalList = await apiAgentSearchStream(
        req,
        (tc) => {
          const name = tc.tool;
          setTraces((prev) => {
            if (!prev.some((t) => t.name === name)) {
              return [...prev, { name, status: "pending", thought: tc.thought }];
            }
            return prev;
          });
          queue.current.push({ kind: "tool", name });
          pump();
        },
        token ?? undefined,
      );
      if (finalList) {
        // 工具轨迹播放完成后渲染结果区
        setViewingList(finalList);
        setCandidates(finalList.candidates);
        const meta = { list_id: finalList.list_id, status: finalList.status };
        setLastViewing(meta);
        localStorage.setItem(LAST_VIEWING_KEY, JSON.stringify(meta));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "找房失败");
    } finally {
      setLoading(false);
    }
  }

  async function onBuildList() {
    setLoading(true);
    setError("");
    try {
      const req = buildReq();
      const vl = await apiCreateViewingList(req, token ?? undefined);
      setViewingList(vl);
      setCandidates(vl.candidates);
      const meta = { list_id: vl.list_id, status: vl.status };
      setLastViewing(meta);
      localStorage.setItem(LAST_VIEWING_KEY, JSON.stringify(meta));
      navigate(`/viewing?id=${vl.list_id}`, { state: { viewingList: vl } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成清单失败");
    } finally {
      setLoading(false);
    }
  }

  const sorted = useMemo(() => {
    const arr = [...candidates];
    if (sortKey === "score") arr.sort((a, b) => b.match_score - a.match_score);
    else if (sortKey === "price_asc") arr.sort((a, b) => a.price - b.price);
    else if (sortKey === "price_desc") arr.sort((a, b) => b.price - a.price);
    else if (sortKey === "area_desc") arr.sort((a, b) => b.area - a.area);
    return arr;
  }, [candidates, sortKey]);

  const stats = useMemo(() => {
    if (candidates.length === 0) return null;
    const prices = candidates.map((c) => c.price);
    const risks = candidates.reduce((n, c) => n + (c.risks?.length ?? 0), 0);
    const avg = Math.round(prices.reduce((a, b) => a + b, 0) / prices.length);
    return { count: candidates.length, avg, min: Math.min(...prices), max: Math.max(...prices), risks };
  }, [candidates]);

  function ringColor(score: number) {
    if (score >= 80) return "#16a34a";
    if (score >= 60) return "#2f7de0";
    return "#d97706";
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 text-white p-6 shadow-card">
        <div className="absolute -right-8 -top-8 h-40 w-40 rounded-full bg-white/10" />
        <div className="absolute right-16 -bottom-12 h-32 w-32 rounded-full bg-accent-500/20" />
        <div className="relative">
          <div className="text-sm text-brand-100/90">智能租房 · 帮你快速找到合适的家</div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">用一句需求，找到最合适的家</h1>
          <p className="mt-1 text-sm text-brand-100/80">
            覆盖真实房源 · 懂你的需求 · 帮你避开租房坑
          </p>
        </div>
      </div>

      {/* 搜索表单 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">描述你的租房需求</h2>
          {history.items.length > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-400">历史：</span>
              <div className="flex flex-wrap gap-1">
                {history.items.slice(0, 4).map((r, i) => (
                  <button
                    key={i}
                    onClick={() => applyReq(r)}
                    className="px-2 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-brand-50 hover:text-brand-600"
                  >
                    {r.district ?? "不限区域"}·{r.max_price}
                  </button>
                ))}
              </div>
              <button onClick={() => history.clear()} className="text-gray-400 hover:text-red-500">
                清空
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">意向区域</label>
            <input
              value={district}
              onChange={(e) => setDistrict(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
              placeholder="如 新吴区"
            />
            <div className="mt-1.5 flex flex-wrap gap-1">
              {DISTRICT_QUICK.map((d) => (
                <button
                  key={d}
                  onClick={() => setDistrict(d)}
                  className={`px-2 py-0.5 rounded text-xs ${district === d ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-brand-50"}`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">最高月租（元）</label>
            <input
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              type="number"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
              placeholder="3000"
            />
            <div className="mt-1.5 flex flex-wrap gap-1">
              {PRICE_QUICK.map((p) => (
                <button
                  key={p}
                  onClick={() => setMaxPrice(String(p))}
                  className={`px-2 py-0.5 rounded text-xs ${Number(maxPrice) === p ? "bg-brand-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-brand-50"}`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">户型</label>
            <div className="flex gap-1.5">
              {ROOM_OPTIONS.map((r) => (
                <button
                  key={r}
                  onClick={() => setRoomType(r)}
                  className={`flex-1 px-2 py-2 rounded-lg text-sm border ${
                    roomType === r
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-gray-300 text-gray-600 hover:border-brand-400"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">通勤目的地（可选）</label>
            <input
              value={commuteTo}
              onChange={(e) => setCommuteTo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
              placeholder="如 软件园"
            />
            <label className="block text-xs text-gray-500 mt-1.5 mb-1">偏好标签（逗号分隔）</label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
              placeholder="近地铁, 拎包入住"
            />
          </div>
        </div>

        {mode === "agent" && (
          <input
            value={userNote}
            onChange={(e) => setUserNote(e.target.value)}
            className="w-full px-3 py-2 mt-4 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-accent-500 focus:outline-none"
            placeholder="补充你的要求（如：不用查风险，只要最便宜的 3 套）"
          />
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-400">找房方式</span>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
            <button
              onClick={() => setMode("pipeline")}
              className={`px-3 py-1.5 ${mode === "pipeline" ? "bg-brand-600 text-white" : "bg-white text-gray-600"}`}
            >
              标准找房
            </button>
            <button
              onClick={() => setMode("agent")}
              className={`px-3 py-1.5 ${mode === "agent" ? "bg-brand-600 text-white" : "bg-white text-gray-600"}`}
            >
              ✦ 智能找房
            </button>
          </div>
          <div className="flex-1" />
          <button
            onClick={onSearch}
            disabled={loading}
            className={`px-5 py-2.5 rounded-lg font-medium text-white shadow-card disabled:opacity-60 ${
              mode === "agent" ? "bg-brand-600 hover:bg-brand-700" : "bg-brand-600 hover:bg-brand-700"
            }`}
          >
            {loading ? "找房中…" : mode === "agent" ? "✦ 智能找房" : "找房"}
          </button>
          {mode === "pipeline" && (
            <button
              onClick={onBuildList}
              disabled={loading}
              className="px-5 py-2.5 rounded-lg border border-brand-500 text-brand-600 font-medium hover:bg-brand-50 disabled:opacity-60"
            >
              生成看房清单
            </button>
          )}
        </div>

        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </div>

      {/* 执行过程：流程步骤条 or Agent 工具轨迹 */}
      {(steps.length > 0 || traces.length > 0) && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <h2 className="font-semibold">
              {mode === "agent" ? "我为你做的这些事" : "为你找房的过程"}
            </h2>
          </div>

          {mode === "agent" ? (
            <div className="space-y-1.5">
              {traces.map((t, i) => (
                <div
                  key={`${t.name}-${i}`}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-sm transition-colors ${
                    t.status === "done"
                      ? "bg-green-50 border-green-200"
                      : t.status === "running"
                        ? "bg-brand-50 border-brand-300"
                        : "bg-gray-50 border-gray-200 text-gray-400"
                  }`}
                >
                  <span className="w-5 text-center font-bold text-gray-400">{i + 1}</span>
                  <span className={`font-medium ${t.status === "done" ? "text-green-700" : t.status === "running" ? "text-brand-600" : ""}`}>
                    {AGENT_TOOL_LABELS[t.name] ?? t.name}
                  </span>
                  {t.status === "running" && (
                    <span className="text-xs text-brand-500 animate-pulse">⟳ 正在处理…</span>
                  )}
                  {t.status === "done" && <span className="text-green-600">✓</span>}
                  {t.thought && t.status === "done" && (
                    <span className="text-xs text-gray-500 truncate ml-2">{t.thought}</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {steps.map((s) => (
                <span
                  key={s.node}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    s.status === "done"
                      ? "bg-green-50 border-green-300 text-green-700"
                      : s.status === "running"
                        ? "bg-blue-50 border-brand-300 text-brand-600 animate-pulse"
                        : "bg-gray-50 border-gray-200 text-gray-400"
                  }`}
                >
                  {s.status === "done" ? "✓ " : s.status === "running" ? "⟳ " : ""}
                  {s.label}
                  {s.status === "running" ? " 执行中…" : s.status === "done" ? `（${s.count}）` : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 结果区 */}
      {candidates.length > 0 && (
        <div className="animate-fadeIn space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-semibold text-lg">为你推荐的房源</h2>
            {stats && (
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="px-2 py-1 rounded bg-gray-100 text-gray-600">命中 {stats.count} 套</span>
                <span className="px-2 py-1 rounded bg-gray-100 text-gray-600">均价 ¥{stats.avg}</span>
                <span className="px-2 py-1 rounded bg-gray-100 text-gray-600">¥{stats.min}–{stats.max}</span>
                <span className={`px-2 py-1 rounded ${stats.risks ? "bg-amber-50 text-amber-700" : "bg-green-50 text-green-700"}`}>
                  {stats.risks ? `${stats.risks} 条风险提示` : "无风险提示"}
                </span>
              </div>
            )}
            <div className="flex-1" />
            <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs">
              {([
                ["score", "匹配度"],
                ["price_asc", "价格↑"],
                ["price_desc", "价格↓"],
                ["area_desc", "面积↓"],
              ] as [SortKey, string][]).map(([k, label]) => (
                <button
                  key={k}
                  onClick={() => setSortKey(k)}
                  className={`px-2.5 py-1.5 ${sortKey === k ? "bg-brand-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-3">
            {sorted.map((c) => (
              <ListingCard
                key={c.id}
                c={c}
                faved={!!favorites.byId[c.id]}
                expanded={!!expanded[c.id]}
                onToggleFav={() => favorites.toggle(c)}
                onToggleExpand={() => setExpanded((p) => ({ ...p, [c.id]: !p[c.id] }))}
                ringColor={ringColor(c.match_score)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 看房清单快捷 */}
      {(viewingList || lastViewing) && (
        <div className="bg-white rounded-2xl border border-green-200 shadow-card p-5 flex flex-wrap items-center gap-4">
          <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
          <div className="text-sm">
            <span className="font-medium">看房清单已生成</span>
            <span className="text-gray-400"> #{viewingList?.list_id ?? lastViewing?.list_id} · {(viewingList?.status ?? lastViewing?.status) === "pending" ? "待确认" : viewVerbal(viewingList?.status ?? lastViewing?.status)}</span>
          </div>
          <div className="flex-1" />
          <button
            onClick={() => navigate(`/viewing?id=${viewingList?.list_id ?? lastViewing?.list_id}`)}
            className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700"
          >
            查看并确认
          </button>
        </div>
      )}
    </div>
  );
}

function viewVerbal(s: string | undefined) {
  if (s === "confirmed") return "已确认";
  if (s === "adjusted") return "已调整";
  return s ?? "";
}

function ListingCard({
  c,
  faved,
  expanded,
  onToggleFav,
  onToggleExpand,
  ringColor,
}: {
  c: CandidateListing;
  faved: boolean;
  expanded: boolean;
  onToggleFav: () => void;
  onToggleExpand: () => void;
  ringColor: string;
}) {
  const riskTop = c.risks?.[0];
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-4 card-hover">
      <div className="flex items-start gap-4">
        {/* 评分环 */}
        <svg width="52" height="52" viewBox="0 0 36 36" className="shrink-0">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#eef2f7" strokeWidth="3" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={ringColor} strokeWidth="3" strokeLinecap="round"
            strokeDasharray={`${c.match_score * 0.888} 100`}
            transform="rotate(-90 18 18)"
          />
          <text x="18" y="22" textAnchor="middle" fontSize="9" fontWeight="700" fill="#334155">
            {Math.round(c.match_score)}
          </text>
        </svg>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="font-semibold truncate">
                {c.title}
                {c.is_verified && (
                  <span className="ml-1.5 text-xs px-1.5 py-0.5 rounded bg-green-50 text-green-700 border border-green-200 align-middle">已核实</span>
                )}
              </div>
              <div className="text-xs text-gray-400 mt-0.5 truncate">
                {c.district} · {c.room_type} · {c.area}㎡
                {c.orientation ? ` · ${c.orientation}` : ""}
                {c.floor ? ` · ${c.floor}` : ""}
              </div>
            </div>
            <button
              onClick={onToggleFav}
              title={faved ? "取消收藏" : "收藏"}
              className="shrink-0 p-1.5 rounded-lg hover:bg-gray-50"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill={faved ? "#dc2626" : "none"} stroke={faved ? "#dc2626" : "#94a3b8"} strokeWidth="2">
                <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z" />
              </svg>
            </button>
          </div>

          <div className="flex items-center gap-2 mt-1">
            <span className="text-xl font-bold text-brand-600">¥{c.price}</span>
            <span className="text-xs text-gray-400">/月</span>
            {riskTop && (
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                riskTop.level === "high" ? "bg-red-50 text-red-700" :
                riskTop.level === "medium" ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-500"
              }`}>
                {riskTop.kind}
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap gap-1 text-xs">
            {(c.match_reasons ?? []).slice(0, 3).map((r, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">{r}</span>
            ))}
            {c.commute_minutes != null && (
              <span className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700">通勤 ~{c.commute_minutes}′</span>
            )}
            {(c.facilities ?? []).slice(0, 3).map((f, i) => (
              <span key={`f${i}`} className="px-1.5 py-0.5 rounded bg-gray-50 text-gray-500">{f}</span>
            ))}
          </div>

          {(c.risks?.length ?? 0) > 0 && (
            <div className="mt-2 space-y-1">
              {(c.risks ?? []).slice(0, expanded ? undefined : 1).map((r, i) => (
                <div key={i} className={`text-xs px-2 py-1 rounded ${
                  r.level === "high" ? "bg-red-50 text-red-700" :
                  r.level === "medium" ? "bg-amber-50 text-amber-700" : "bg-gray-50 text-gray-600"
                }`}>
                  [{r.kind}] {r.detail}
                  {r.reference && <span className="text-gray-400"> · 依据 {r.reference}</span>}
                </div>
              ))}
            </div>
          )}

          {(expanded || (c.risks?.length ?? 0) > 1) && (
            <button onClick={onToggleExpand} className="mt-2 text-xs text-brand-600 hover:underline">
              {(c.risks?.length ?? 0) > 1 && !expanded
                ? `展开全部 ${c.risks?.length} 条风险`
                : expanded
                  ? "收起"
                  : ""}
            </button>
          )}

          {expanded && (c.description || c.address || c.listing_date || c.source) && (
            <div className="mt-2 pt-2 border-t border-gray-100 text-xs text-gray-500 space-y-1">
              {c.description && <p>{c.description}</p>}
              {c.address && <p>地址：{c.address}</p>}
              <p>
                {c.listing_date && `发布 ${c.listing_date}`}
                {c.url && <> · <a className="text-brand-600 hover:underline" href={c.url} target="_blank" rel="noreferrer">查看详情</a></>}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
