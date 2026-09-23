// 作者：zcy
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiLogin } from "../api";
import { useAuth } from "../store/auth";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const login = useAuth((s) => s.login);
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const resp = await apiLogin({ username, password });
      login(resp, username);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  const demo = [
    ["admin", "admin123", "管理员"],
    ["user", "user123", "普通用户"],
    ["audit", "audit123", "审计"],
  ];

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm animate-fadeIn">
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 text-white p-8 text-center shadow-card mb-6">
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-white/10" />
          <div className="absolute -left-8 -bottom-12 h-24 w-24 rounded-full bg-accent-500/25" />
          <div className="relative">
            <div className="text-3xl font-extrabold tracking-tight">RentAI</div>
            <p className="text-sm text-brand-100/90 mt-1">企业级智能租房助手</p>
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-white rounded-2xl p-6 shadow-card border border-gray-200 space-y-4"
        >
          <div>
            <label className="block text-sm text-gray-600 mb-1">用户名</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="请输入用户名"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="••••••••"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-60"
          >
            {loading ? "登录中…" : "登录"}
          </button>

          <div>
            <div className="text-xs text-gray-400 mb-1.5">演示账号（多租户 RBAC）</div>
            <div className="grid grid-cols-3 gap-1.5">
              {demo.map(([u, p, role]) => (
                <button
                  key={u}
                  type="button"
                  onClick={() => {
                    setUsername(u);
                    setPassword(p);
                  }}
                  className="px-1.5 py-1.5 rounded-lg border border-gray-200 text-xs hover:border-brand-400 hover:bg-brand-50"
                >
                  <div className="font-medium text-gray-700">{u}</div>
                  <div className="text-gray-400">{role}</div>
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
