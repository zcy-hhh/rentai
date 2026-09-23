// 作者：zcy
import { Navigate, Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import ViewingListPage from "./pages/ViewingList";
import Favorites from "./pages/Favorites";
import Knowledge from "./pages/Knowledge";
import Observe from "./pages/Observe";
import { useAuth } from "./store/auth";

export default function App() {
  const token = useAuth((s) => s.token);
  return (
    <ErrorBoundary>
      <Routes>
        <Route
          path="/login"
          element={token ? <Navigate to="/" replace /> : <Login />}
        />
        <Route element={<Layout />}>
          <Route path="/" element={<Chat />} />
          <Route path="/viewing" element={<ViewingListPage />} />
          <Route path="/favorites" element={<Favorites />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/observe" element={<Observe />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
