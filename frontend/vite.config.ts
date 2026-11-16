import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Coolade Gateway frontend — Vite config.
// Dev proxy: forwards /api and /v1 to the (future) nginx front door per TECH.md §2.
// This lets `vite dev` work standalone against a locally running backend stack
// without CORS configuration, mirroring how nginx will route in production.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8085',
        changeOrigin: true,
      },
      '/v1': {
        target: 'http://localhost:8085',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
