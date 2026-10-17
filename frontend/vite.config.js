import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react(), tailwindcss()],
    base: "./",
    server: {
      host: true,
      allowedHosts: true,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        "/auth": {
          target: apiProxyTarget,
          changeOrigin: false,
        },
      },
    },
    build: {
      outDir: "dist",
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
              return "react";
            }
            if (id.includes("node_modules/recharts/")) {
              return "recharts";
            }
            if (id.includes("node_modules/lucide-react/")) {
              return "icons";
            }
            return undefined;
          },
        },
      },
      chunkSizeWarningLimit: 1500,
    },
  };
});
