// 作者：zcy
import { useEffect, useRef, useState } from "react";
import { apiChat, apiSaveViewing } from "../api";
import { AGENT_TOOL_LABELS, type CandidateListing, type ChatStepResult } from "../types";

interface Msg {
  role: "user" | "assistant";
  kind: "clarify" | "message" | "result" | "escalate" | "error" | "";
  text: string;
  result?: ChatStepResult;
}

function scoreColor(s: number) {
  if (s >= 85) return "#16a34a";
  if (s >= 70) return "#2563c8";
  if (s >= 55) return "#d97706";
  return "#dc2626";
}

function ResultCard({ c }: { c: CandidateListing }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-800 truncate">{c.title}</div>
          <div className="mt-0.5 text-xs text-slate-500">
            {c.district} · {c.room_type} · {c.area}㎡ · {c.orientation || "-"}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-base font-bold" style={{ color: scoreColor(c.match_score) }}>
            {Math.round(c.match_score)}
          </span>
          <span className="text-xs text-slate-400">分</span>
        </div>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span className="text-lg font-bold text-brand-700">¥{Math.round(c.price)}<span className="text-xs font-normal text-slate-400">/月</span></span>
        {c.is_verified && <span className="text-[11px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">已核实</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {(c.facilities || []).slice(0, 4).map((f) => (
          <span key={f} className="text-[11px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{f}</span>
        ))}
      </div>
      {(c.risks || []).length > 0 && (
        <div className="mt-1.5 text-[11px] text-amber-700">
          ⚠ {c.risks[0].kind}：{c.risks[0].detail}
        </div>
      )}
      {c.url && (
        <a
          href={c.url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700"
        >
          查看真实房源 ↗
        </a>
      )}
    </div>
  );
}

function TraceRow({ trace }: { trace: { tool: string; thought?: string }[] }) {
  if (!trace || !trace.length) return null;
  return (
    <div className="mb-2 rounded-xl border border-blue-100 bg-blue-50/70 p-3">
      <div className="mb-1.5 text-xs font-semibold text-brand-700">我为你做了这些事</div>
      <div className="flex flex-wrap items-center gap-1.5">
        {trace.map((t, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span className="rounded-md bg-white border border-brand-200 px-2 py-0.5 text-xs text-brand-700">
              {AGENT_TOOL_LABELS[t.tool] ?? "处理中"}
            </span>
            {i < trace.length - 1 && <span className="text-brand-300">→</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

function ReflexionView({ reflexion }: { reflexion: { round: number; issues: string[]; improvement: string }[] }) {
  if (!reflexion || !reflexion.length) return null;
  return (
    <div className="mb-2 rounded-xl border border-amber-200 bg-amber-50/70 p-3">
      <div className="mb-1.5 text-xs font-semibold text-amber-700">帮你调整了找房方案</div>
      {reflexion.map((r) => (
        <div key={r.round} className="text-xs text-amber-800">
          <div className="font-medium">第 {r.round} 次调整 · {r.improvement}</div>
        </div>
      ))}
    </div>
  );
}

function EscalationCard({ esc }: { esc: { reason: string[]; context: string; advice: string } }) {
  return (
    <div className="mb-2 rounded-xl border border-red-200 bg-red-50/80 p-3">
      <div className="mb-1 text-xs font-semibold text-red-700">已为你转接人工客服</div>
      <div className="text-xs text-red-800">原因：{esc.reason.join("；")}</div>
      <div className="mt-1 text-[11px] text-red-600/90">{esc.advice}</div>
    </div>
  );
}

export default function Chat() {
  const SESSION_KEY = "rentai-chat-session";
  // 会话持久化：sessionId 与消息写入 localStorage，返回页面/刷新/跳转后自动恢复（同一 session 后端多轮继续）
  const [sessionId, setSessionId] = useState<string>(
    () => localStorage.getItem(SESSION_KEY) ?? `chat-${Date.now()}`,
  );
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try {
      const sid = localStorage.getItem(SESSION_KEY);
      const raw = sid ? localStorage.getItem(`rentai-chat-msgs-${sid}`) : null;
      return raw ? (JSON.parse(raw) as Msg[]) : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [savedIds, setSavedIds] = useState<Record<number, string>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, sessionId);
    localStorage.setItem(`rentai-chat-msgs-${sessionId}`, JSON.stringify(msgs));
  }, [msgs, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", kind: "", text: msg }]);
    setBusy(true);
    try {
      // 前端本地保存了完整历史（localStorage），作为上下文真相源传给后端（后端 Redis 记忆可能过期）
      const hist = msgs.filter((m) => m.text).map((m) => [m.role, m.text] as [string, string]);
      const r: ChatStepResult = await apiChat(msg, sessionId, hist);
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          kind: r.kind,
          text: r.text ?? (r.kind === "result" ? "为你找到这些房源：" : r.kind === "escalate" ? "暂时没找到完全匹配的，已为你转接人工客服。" : ""),
          result: r,
        },
      ]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", kind: "error", text: `出错了：${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    const s = `chat-${Date.now()}`;
    setMsgs([]);
    setSessionId(s); // 触发持久化 effect：新 session 写入空会话
  }

  async function handleSave(idx: number) {
    const m = msgs[idx];
    const cands = m?.result?.viewing?.candidates ?? [];
    if (!m?.result?.requirement || !cands.length) return;
    try {
      const vl = await apiSaveViewing(m.result.requirement, cands);
      setSavedIds((s) => ({ ...s, [idx]: vl.list_id }));
      localStorage.setItem("rentai:last_viewing", JSON.stringify({ list_id: vl.list_id }));
    } catch (e) {
      alert("保存失败：" + (e as Error).message);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-64px)] max-w-3xl flex-col px-4 pt-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">智能找房</h1>
          <p className="text-xs text-slate-500">用一句话告诉我你想租什么样的房子，我帮你找到合适的房源</p>
        </div>
        <button onClick={reset} className="rounded-lg border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50">
          新会话
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-xl bg-slate-50 p-3">
        {msgs.length === 0 && (
          <div className="flex h-full items-center justify-center text-center">
            <div className="max-w-sm rounded-xl bg-white p-5 shadow-sm">
              <div className="mb-1 text-sm font-semibold text-slate-700">试试这样说</div>
              <div className="space-y-1 text-left text-xs text-slate-500">
                <div>· “帮我找滨湖 3000 以内的 1 室”</div>
                <div>· “只要最便宜的三套，近地铁的”</div>
                <div>· “不用查风险，直接给我清单”</div>
              </div>
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm ${
                m.role === "user"
                  ? "bg-brand-600 text-white"
                  : m.kind === "error"
                    ? "bg-red-50 text-red-700 border border-red-200"
                    : "bg-white text-slate-700 shadow-sm border border-slate-200"
              }`}
            >
              {m.text && <div className={m.result ? "mb-2" : ""}>{m.text}</div>}
              {m.result && m.result.kind === "result" && (
                <div>
                  <TraceRow trace={m.result.trace ?? []} />
                  <ReflexionView reflexion={m.result.reflexion ?? []} />
                  {m.result.requirement && (
                    <div className="mb-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600">
                      你想找：{m.result.requirement.district || "不限区域"} · 预算 {m.result.requirement.max_price}元 ·
                      {m.result.requirement.room_types?.join("/")}
                      {m.result.requirement.tags?.length ? ` · ${m.result.requirement.tags.join("、")}` : ""}
                    </div>
                  )}
                  {(m.result.viewing?.candidates ?? []).length ? (
                    <div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {m.result.viewing!.candidates.map((c) => (
                          <ResultCard key={c.id} c={c} />
                        ))}
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        {savedIds[i] ? (
                          <a
                            href={`/viewing?id=${savedIds[i]}`}
                            className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
                          >
                            ✓ 已保存为看房清单 · 查看 →
                          </a>
                        ) : (
                          <button
                            onClick={() => handleSave(i)}
                            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
                          >
                            保存为看房清单
                          </button>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-500">未找到合适房源，试试补充区域或预算。</div>
                  )}
                </div>
              )}
              {m.result && m.result.kind === "escalate" && (
                <div>
                  <TraceRow trace={m.result.trace ?? []} />
                  <ReflexionView reflexion={m.result.reflexion ?? []} />
                  {m.result.escalation && <EscalationCard esc={m.result.escalation} />}
                  <div className="text-xs text-red-500">已保存你的找房需求，客服会继续为你跟进。</div>
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-white px-3.5 py-2 text-sm text-slate-500 shadow-sm border border-slate-200">
              <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
              正在帮你找房…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="py-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)}
            placeholder="说说你想租什么样的房子…"
            className="flex-1 rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
          />
          <button
            onClick={() => send(input)}
            disabled={busy || !input.trim()}
            className="rounded-xl bg-brand-600 px-5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-40"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
