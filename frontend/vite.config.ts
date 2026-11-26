import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API runs separately (uvicorn on :8000); Vite proxies /api so the
// browser sees one origin, exactly as in production where FastAPI serves the built files.
const API_TARGET = process.env.STEGOSHIELD_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    assetsInlineLimit: 0,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
