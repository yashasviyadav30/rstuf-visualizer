/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The backend serves the built files from one origin in every deployment, so
// the interface asks for `/api/v1/...` with no host in front of it. That only
// works during development if something forwards those paths, which is what
// the proxy below does: the dev server answers for the interface and hands
// anything under /api or /healthz to the backend.
//
// RSTUF_CORS_ORIGINS exists for the other arrangement, where the interface is
// served from somewhere the backend does not control and the browser really
// is talking to two origins.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/healthz': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
});
