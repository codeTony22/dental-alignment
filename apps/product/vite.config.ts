import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The product app runs BESIDE the frozen demo (plan §3): demo web is :5173 → :8000,
// product is :5174 → the BFF on :8001. Same proxy pattern as apps/web's vite.config —
// the app talks only to its own origin and the dev server forwards to the BFF, so the
// presentational tier never hard-codes a backend host.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      // the BFF's liveness probe lives at /health (not under /api); the shell pings it
      "/health": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
});
