import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Lira 利润诊断",
        short_name: "Lira",
        description: "本地电商利润诊断",
        theme_color: "#16202e",
        background_color: "#f4f6f9",
        display: "standalone",
        icons: [
          { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8010",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
