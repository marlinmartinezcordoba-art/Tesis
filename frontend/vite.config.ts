import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo (npm run dev) Vite reenvía /api al backend FastAPI local.
// En producción la interfaz compilada la sirve el mismo backend.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.RICORA_API || "http://localhost:8000", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: false },
});
