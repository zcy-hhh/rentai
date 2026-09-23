// 作者：zcy
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 前端 dev server 代理 /api 到后端 FastAPI（绕 CORS）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
