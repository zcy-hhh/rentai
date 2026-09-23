// 作者：zcy
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";

export default function Layout() {
  const token = useAuth((s) => s.token);
  const username = useAuth((s) => s.username);
  const role = useAuth((s) => s.role);
  const logout = useAuth((s) => s.logout);
  const navigate = useNavigate();

  if (!token) return <Navigate to="/login" replace />;

  const navClass = ({ isActive }: { isActive: boolean }) =>
    "px-3 py-2 rounded-lg text-sm font-medium transition-colors " +
    (isActive
      ? "bg-brand-600 text-white"
      : "text-gray-600 hover:bg-gray-100");

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="font-bold text-brand-600 text-lg">RentAI</span>
            <nav className="flex items-center gap-1">
              <NavLink to="/" className={navClass} end>
                智能助手
              </NavLink>
              <NavLink to="/viewing" className={navClass}>
                看房清单
              </NavLink>
              <NavLink to="/knowledge" className={navClass}>
                租房知识库
              </NavLink>
              <NavLink to="/favorites" className={navClass}>
                我的收藏
              </NavLink>
              <NavLink to="/observe" className={navClass}>
                观测台
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-gray-500">
            <span>
              {username}
              {role ? ` · ${role}` : ""}
            </span>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="text-gray-400 hover:text-gray-700"
            >
              退出
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
