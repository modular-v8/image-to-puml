import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_ORIGIN = "http://127.0.0.1:8765";

// Build output lands inside the Python package so `uv_build` ships it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: {
    outDir: path.resolve(import.meta.dirname, "../src/umlregen/ui/static"),
    emptyOutDir: true,
  },
  // `pnpm dev` proxies to a running `uml-regen serve`.
  server: { proxy: { "/api": API_ORIGIN } },
});
