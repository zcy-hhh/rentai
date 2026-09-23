// 作者：zcy
import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { apiConfirm, apiGetViewing } from "../api";
import type { ViewingList } from "../types";

const STATUS_META: Record<string, { label: string; dot: string; badge: string }> = {
  pending: { label: "待确认", dot: "bg-blue-500", badge: "bg-blue-50 text-blue-700 border-blue-300" },
  confirmed: { label: "已确认", dot: "bg-green-500", badge: "bg-green-50 text-green-700 border-green-300" },
  adjusted: { label: "已调整", dot: "bg-amber-500", badge: "bg-amber-50 text-amber-700 border-amber-300" },
};

// 无 id 时兜底：读 localStorage 里最近一次清单（导航入口进入也能复用）
function readLastViewingId(): string | null {
  try {
    const raw = localStorage.getItem("rentai:last_viewing");
    if (!raw) return null;
    const meta = JSON.parse(raw) as { list_id?: string };
    return meta.list_id ?? null;
  } catch {
    return null;
  }
}

export default function ViewingListPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const urlId = searchParams.get("id"); // 复用：?id=xxx 直接按 id 从 PG 读回
  const initial = (location.state as { viewingList?: ViewingList })?.viewingList ?? null;
  const [list, setList] = useState<ViewingList | null>(initial);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // 无 state（刷新/直接进入/导航入口）时：按 URL id 或最近清单 id 从 PostgreSQL 复用读回
  useEffect(() => {
    if (list) return;
    const id = urlId || readLastViewingId();
    if (id) {
      apiGetViewing(id).then(setList).catch(() => setList(null));
    }
  }, [urlId, list]);

  async function onAction(action: "confirm" | "adjust") {
    if (!list) return;
    setLoading(true);
    setError("");
    try {
      const updated = await apiConfirm(list.list_id, action, note);
      setList(updated);
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setLoading(false);
    }
  }

  if (!list) {
    return (
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-12 text-center">
        <div className="text-4xl mb-3">📋</div>
        <p className="text-gray-400">暂无看房清单。请先在「智能搜索」页生成看房清单。</p>
      </div>
    );
  }

  const meta = STATUS_META[list.status] ?? STATUS_META.pending;
  const r = list.requirement;

  return (
    <div className="space-y-4 animate-fadeIn">
      {/* 头部 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold text-lg">
            看房清单 <span className="text-gray-400 text-sm">#{list.list_id}</span>
          </h2>
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm border ${meta.badge}`}>
            <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
            {meta.label}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400">区域</div>
            <div className="font-medium mt-0.5">{r.district ?? "不限"}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400">预算</div>
            <div className="font-medium mt-0.5">¥{r.max_price}/月以内</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400">户型</div>
            <div className="font-medium mt-0.5">{r.room_types?.join("/") ?? "不限"}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-400">面积</div>
            <div className="font-medium mt-0.5">{r.min_area ? `≥ ${r.min_area}㎡` : "不限"}</div>
          </div>
        </div>
        {r.commute_to && (
          <div className="mt-2 text-xs text-gray-500">
            通勤：{r.commute_to}{r.commute_max_minutes ? `（上限 ${r.commute_max_minutes} 分钟）` : ""}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* 核实项与问询 */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
          <h3 className="font-semibold mb-3 text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-500" /> 现场需核实项
          </h3>
          <ul className="space-y-1.5 text-sm">
            {list.verify_items.map((v, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 flex h-4 w-4 items-center justify-center rounded border border-brand-300 text-brand-600 text-xs">✓</span>
                {v}
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
          <h3 className="font-semibold mb-3 text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500" /> 问询房东/中介
          </h3>
          <ul className="space-y-1.5 text-sm">
            {list.ask_items.map((v, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 text-amber-500">?</span>
                {v}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* 候选 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <h3 className="font-semibold mb-3 text-sm">清单房源（{list.candidates.length}）</h3>
        <div className="space-y-2">
          {list.candidates.map((c) => (
            <div key={c.id} className="flex items-center justify-between border border-gray-100 rounded-lg p-3 hover:border-brand-200 hover:bg-brand-50/30 transition-colors">
              <div>
                <div className="text-sm font-medium">{c.title}</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {c.district} · {c.room_type} · {c.area}㎡
                </div>
                {(c.risks?.length ?? 0) > 0 && (
                  <div className="mt-1 text-xs text-amber-700">
                    ⚠ {(c.risks ?? []).slice(0, 1).map((x) => x.kind).join(", ")}
                  </div>
                )}
              </div>
              <div className="text-right shrink-0 ml-3">
                <div className="font-bold text-brand-600">¥{c.price}/月</div>
                <div className="text-xs text-gray-400">匹配 {c.match_score}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 确认 / 调整 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <h3 className="font-semibold mb-1 text-sm">确认 · 调整</h3>
        <p className="text-xs text-gray-400 mb-3">
          <b className="text-gray-500">确认</b> = 决定就去这几套，我会记住你的偏好，之后优先推荐更贴近的房源；<br />
          <b className="text-gray-500">调整</b> = 这套方案不满意，补充原因后我按你的新要求重新为你找。
          确认/调整结果都会保存，换设备也不丢。
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
            placeholder="备注（调整原因等，可选）"
          />
          <button
            onClick={() => onAction("confirm")}
            disabled={loading}
            className="px-4 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 disabled:opacity-60"
          >
            确认看房
          </button>
          <button
            onClick={() => onAction("adjust")}
            disabled={loading}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-60"
          >
            调整清单
          </button>
        </div>
      </div>
    </div>
  );
}
