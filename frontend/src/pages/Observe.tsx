// 作者：zcy
import { useCallback, useEffect, useState } from "react";
import { apiObserveMetrics, apiObserveRagas, type ObserveSummary } from "../api";

// 观测后台：评测指标（确定性/Agent 决策/Ragas 语义）+ 可观测统计 + 数据基线
export default function Observe() {
  const [data, setData] = useState<ObserveSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ragas, setRagas] = useState<Record<string, unknown> | null>(null);
  const [ragasLoading, setRagasLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiObserveMetrics());
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // 自动轮询：对话轮次 / 用量 / 数据规模等指标实时刷新（页面停留即可看到变化）
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  const runRagas = async () => {
    setRagasLoading(true);
    setError("");
    try {
      setRagas(await apiObserveRagas(3));
    } catch (e) {
      setError(e instanceof Error ? e.message : "语义评测失败");
    } finally {
      setRagasLoading(false);
    }
  };

  const bar = (v: number | undefined) => (
    <div className="h-2 w-full bg-gray-200 rounded-full overflow-hidden">
      <div
        className="h-full bg-brand-600 rounded-full"
        style={{ width: `${Math.min(100, Math.max(0, (v ?? 0) * 100))}%` }}
      />
    </div>
  );

  const metricCard = (label: string, value: number | null | undefined, sub?: string) => {
    const v = typeof value === "number" && Number.isFinite(value) ? value : null;
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="text-sm text-gray-500 mb-1">{label}</div>
        <div className="text-2xl font-semibold text-brand-600">
          {v === null ? "—" : v.toFixed(3)}
        </div>
        {bar(v ?? undefined)}
        {sub ? <div className="text-xs text-gray-400 mt-1">{sub}</div> : null}
      </div>
    );
  };

  const stat = (label: string, value: number | string | undefined) => (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="text-xl font-semibold mt-1">
        {typeof value === "number" && value % 1 !== 0 ? value.toFixed(2) : value ?? "—"}
      </div>
    </div>
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-900">观测台</h1>
          <p className="text-sm text-gray-500">评测指标 · 对话用量 · 数据规模（后台自观测，生产可接 Langfuse/OTel）{lastUpdated ? ` · 更新于 ${lastUpdated}` : ""}</p>
        </div>
        <button
          onClick={load}
          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-sm font-medium rounded-lg"
        >
          刷新
        </button>
      </div>

      {error ? <div className="bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg px-4 py-3 mb-4">{error}</div> : null}

      {loading && !data ? (
        <div className="text-gray-400 text-sm py-10 text-center">加载中…</div>
      ) : data ? (
        <div className="space-y-6">
          {/* 1. 结果质量评测 */}
          <section>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">评测 · 结果质量（确定性）</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {metricCard("匹配精确率 match_precision@k", data.metrics["match_precision@k"], `${data.metrics.match_cases} 条标注用例`)}
              {metricCard("匹配召回率 match_recall", data.metrics.match_recall, "应命中中被返回的占比")}
              {metricCard("避坑召回率 risk_recall", data.metrics.risk_recall, `${data.metrics.risk_cases} 条坑房源用例`)}
              {metricCard("Agent 决策质量 avg_decision_score", data.decision.avg_decision_score / 100, "工具覆盖/顺序/无重复/尊重指令")}
            </div>
          </section>

          {/* 2. 语义评测（ragas） */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700">评测 · 语义指标（Ragas + qwen）</h2>
              <button
                onClick={runRagas}
                disabled={ragasLoading}
                className="px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg"
              >
                {ragasLoading ? "评测中…" : "运行语义评测"}
              </button>
            </div>
            {ragas ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {metricCard("忠实度 faithfulness", ragas["faithfulness"] as number | undefined, "答案忠于检索上下文")}
                {metricCard("上下文精确度 context_precision", ragas["llm_context_precision_without_reference"] as number | undefined)}
              </div>
            ) : (
              <div className="bg-white border border-dashed border-gray-300 rounded-xl p-6 text-center text-sm text-gray-400">
                点击按钮，调用 ragas 对标注用例跑语义评测（会消耗少量 LLM 用量）
              </div>
            )}
          </section>

          {/* 3. 可观测：对话用量 */}
          <section>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">可观测 · 对话用量（进程内累计）</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              {stat("对话轮次", data.usage.chat_turns)}
              {stat("LLM 调用次数", data.usage.llm_calls)}
              {stat("累计 token", data.usage.total_tokens)}
              {stat("平均延迟(ms)", data.usage.avg_latency_ms)}
              {stat("估算成本(元)", data.usage.est_cost)}
            </div>
          </section>

          {/* 4. 数据基线 */}
          <section>
            <h2 className="text-sm font-semibold text-gray-700 mb-3">数据规模</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {stat("房源 listings", data.data.listings)}
              {stat("看房清单 viewings", data.data.viewings)}
              {stat("文档知识块 doc_chunks", data.data.doc_chunks)}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
