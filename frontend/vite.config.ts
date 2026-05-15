import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9120",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
