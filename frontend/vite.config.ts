import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Dev: frontend (5173) → backend (8000). Production memakai nginx proxy.
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
