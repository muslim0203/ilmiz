import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // Preview harness porti PORT orqali keladi; bo'lmasa odatiy 5173.
    port: Number(process.env.PORT) || 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
