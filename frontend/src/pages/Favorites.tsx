// 作者：zcy
import { useNavigate } from "react-router-dom";
import { useFavorites } from "../store/favorites";
import type { CandidateListing } from "../types";

export default function Favorites() {
  const favorites = useFavorites();
  const navigate = useNavigate();
  const items = favorites.order
    .map((id) => favorites.byId[id])
    .filter(Boolean);

  if (items.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-12 text-center">
        <div className="text-4xl mb-3">🏠</div>
        <p className="text-gray-400">还没有收藏的房源。去「智能搜索」页点亮卡片右上角的 ♡ 收藏。</p>
        <button
          onClick={() => navigate("/")}
          className="mt-4 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700"
        >
          去搜索
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-lg">我的收藏（{items.length}）</h2>
        <button
          onClick={() => favorites.clear()}
          className="text-xs text-gray-400 hover:text-red-500"
        >
          清空收藏
        </button>
      </div>
      <div className="grid lg:grid-cols-2 gap-3">
        {items.map((c) => (
          <FavCard key={c.id} c={c} onRemove={() => favorites.toggle(c)} onSearch={() => navigate("/")} />
        ))}
      </div>
    </div>
  );
}

function FavCard({
  c,
  onRemove,
  onSearch,
}: {
  c: CandidateListing;
  onRemove: () => void;
  onSearch: () => void;
}) {
  const riskTop = c.risks?.[0];
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="font-semibold truncate">{c.title}</div>
          <div className="text-xs text-gray-400 mt-0.5">
            {c.district} · {c.room_type} · {c.area}㎡ · 评分 {c.match_score}
          </div>
        </div>
        <button
          onClick={onRemove}
          className="p-1.5 rounded-lg text-red-500 hover:bg-red-50"
          title="取消收藏"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="#dc2626" stroke="#dc2626" strokeWidth="2">
            <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z" />
          </svg>
        </button>
      </div>
      <div className="flex items-center gap-2 mt-2">
        <span className="text-xl font-bold text-brand-600">¥{c.price}</span>
        <span className="text-xs text-gray-400">/月</span>
        {riskTop && (
          <span className={`text-xs px-1.5 py-0.5 rounded ${
            riskTop.level === "high" ? "bg-red-50 text-red-700" :
            riskTop.level === "medium" ? "bg-amber-50 text-amber-700" : "bg-gray-100 text-gray-500"
          }`}>{riskTop.kind}</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1 text-xs">
        {(c.match_reasons ?? []).slice(0, 3).map((r, i) => (
          <span key={i} className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">{r}</span>
        ))}
        {c.commute_minutes != null && (
          <span className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700">通勤 ~{c.commute_minutes}′</span>
        )}
      </div>
      <button
        onClick={onSearch}
        className="mt-3 w-full py-1.5 rounded-lg border border-brand-300 text-brand-600 text-sm hover:bg-brand-50"
      >
        按此需求再去搜索
      </button>
    </div>
  );
}
