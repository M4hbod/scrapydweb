import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // FastAPI backend (run `just dev` or `just up`)
      "/api": "http://127.0.0.1:5000",
      "/static": "http://127.0.0.1:5000",
      "/metadata": "http://127.0.0.1:5000",
      // legacy node-prefixed JSON endpoints still used for actions (tasks.xhr, scrapyd api)
      "^/\\d+/.*": { target: "http://127.0.0.1:5000" },
    },
  },
})
