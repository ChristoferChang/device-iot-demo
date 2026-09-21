import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Fresh filename prefixes bust the Apps edge cache when a deploy goes
        // sideways (a stale cached chunk mix produced TDZ crashes on live
        // while the identical bundle worked served locally).
        entryFileNames: "assets/app-[hash].js",
        chunkFileNames: "assets/app-[hash].js",
        assetFileNames: "assets/app-[hash][extname]",
      },
    },
  },
});
