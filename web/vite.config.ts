import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 部署口子：Qoder Sites 上只有静态文件，API 在 ECS。
// VITE_API_BASE 留空时走相对路径 —— 本地 dev 由下面的 proxy 转到 127.0.0.1:8000，
// 生产由 Caddy 同域反代，前端代码里不出现任何环境判断。
const API_TARGET = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000";
// /docs 与 /openapi.json 一起转发：落地页页脚要能跳到后端接口文档
const PROXY = {
  "/api": { target: API_TARGET, changeOrigin: true },
  "/docs": { target: API_TARGET, changeOrigin: true },
  "/openapi.json": { target: API_TARGET, changeOrigin: true },
};

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173, proxy: PROXY },
  // preview 不继承 server.proxy；不补这一段，`npm run preview` 一条数据都拉不到，
  // 部署前就没法用和生产同形态的静态构建做冒烟测试。
  preview: { port: 4173, proxy: PROXY },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // 图表与流程图都走 React.lazy：首屏（落地页）只加载 index + react-vendor，
        // 这两个大块按页面访问时才拉取，避免 700KB+ 的首屏 JS。
        // d3 同时被 recharts 与 @xyflow 使用，单独成块，避免 charts <-> flow 循环依赖。
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id)) return "react-vendor";
          if (id.includes("node_modules/@xyflow")) return "flow";
          if (id.includes("node_modules/recharts") || id.includes("node_modules/victory-vendor")) return "charts";
          if (id.includes("/node_modules/d3-") || id.includes("/node_modules/internmap/")) return "d3";
          return undefined;
        },
      },
    },
  },
});
