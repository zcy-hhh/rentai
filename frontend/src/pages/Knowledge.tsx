// 作者：zcy
import { useRef, useState } from "react";
import { apiDocIngest, apiDocSearch, type DocHit, type DocSearchResult } from "../api";

const ALLOWED = [".pdf", ".pptx", ".xlsx", ".xls", ".txt", ".md", ".csv"];

function hitLabel(h: DocHit): string {
  const loc = h.sheet ? `「${h.sheet}」表` : `第 ${h.page} 页`;
  return `${h.source_name} · ${loc}`;
}

function scoreLabel(score: number): { text: string; cls: string } {
  if (score >= 0.7) return { text: "高度相关", cls: "text-green-600 bg-green-50" };
  if (score >= 0.5) return { text: "相关", cls: "text-brand-600 bg-brand-50" };
  return { text: "一般相关", cls: "text-gray-500 bg-gray-100" };
}

export default function Knowledge() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DocSearchResult | null>(null);
  const [error, setError] = useState("");

  async function onUpload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setUploading(true);
    setUploadMsg("");
    setError("");
    try {
      await apiDocIngest(f, (chunks) => {
        setUploadMsg(`《${f.name}》已解析完成（${chunks} 段），可以在下方开始提问。`);
      });
      if (fileRef.current) fileRef.current.value = "";
      setFileName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "文档解析失败");
    } finally {
      setUploading(false);
    }
  }

  async function onSearch() {
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setError("");
    try {
      setResult(await apiDocSearch(query));
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 animate-fadeIn">
      {/* 上传区 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <h2 className="font-semibold text-lg mb-1">租房知识库</h2>
        <p className="text-sm text-gray-400 mb-4">
          上传合同、政策、行情表等文档，我帮你记下来，之后提问能直接给出答案和出处。
        </p>
        <div className="flex flex-col sm:flex-row gap-3 items-stretch">
          <input
            ref={fileRef}
            type="file"
            accept={ALLOWED.join(",")}
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          <button
            onClick={onUpload}
            disabled={uploading || !fileName}
            className="px-5 py-2 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {uploading ? "解析中…" : "上传文档"}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          支持：PDF、PPT、Excel、纯文本。上传的文档会自动整理成可检索的内容。
        </p>
        {uploadMsg && <p className="mt-3 text-sm text-green-600">{uploadMsg}</p>}
      </div>

      {/* 检索区 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-5">
        <h3 className="font-semibold text-sm mb-3">问一个租房问题</h3>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:outline-none"
            placeholder="例如：押金退还要注意什么？群租怎么认定？蠡湖新城月租多少？"
          />
          <button
            onClick={onSearch}
            disabled={loading || !q.trim()}
            className="px-5 py-2 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? "检索中…" : "提问"}
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </div>

      {/* 结果 */}
      {result && (
        <div className="space-y-2">
          <div className="text-sm text-gray-500">
            关于「{result.query}」找到 {result.count} 条相关说明：
          </div>
          {result.hits.map((h, i) => {
            const tag = scoreLabel(h.score);
            return (
              <div key={i} className="bg-white rounded-2xl border border-gray-200 shadow-card p-4">
                <div className="flex items-center gap-2 text-xs mb-2">
                  <span className="px-2 py-0.5 rounded-full border border-gray-200 text-gray-600">
                    {hitLabel(h)}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full ${tag.cls}`}>{tag.text}</span>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed">{h.text}</p>
              </div>
            );
          })}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-card p-8 text-center text-sm text-gray-400">
          上传文档后，在这里输入问题即可得到带出处的回答。
        </div>
      )}
    </div>
  );
}
