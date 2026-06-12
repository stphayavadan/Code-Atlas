import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend so the frontend can use
// same-origin relative URLs and avoid CORS friction during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9500",
        changeOrigin: true,
      },
    },
  },
});
