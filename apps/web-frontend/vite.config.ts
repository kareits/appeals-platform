/// <reference types="vitest/config" />
/// <reference types="node" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite build and dev-server configuration for the web frontend.
 *
 * In development, requests to `/api` are proxied to the platform edge (the Caddy reverse proxy in
 * front of the BFF) so the SPA speaks to the same-origin `/api/v1` surface it uses in production.
 * The proxy target is overridable with `VITE_API_PROXY_TARGET` to match a non-default `HTTP_PORT`.
 * The dev and preview servers bind to loopback only so no dev/test HTTP surface is exposed on the
 * network (CR-WEB-MEDIUM-004).
 */
export default defineConfig(() => {
  const proxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8080";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 4173,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./vitest.setup.ts"],
      css: false,
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
