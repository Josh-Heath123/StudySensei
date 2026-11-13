/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type ProxyOptions } from "vite";

// The web app calls the API on its own origin under /api; Vite forwards those
// requests to the API, so development has no cross-origin requests at all.
const apiProxy: Record<string, ProxyOptions> = {
  "/api": {
    target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: { port: 5173, strictPort: true, proxy: apiProxy },
  preview: { proxy: apiProxy },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
