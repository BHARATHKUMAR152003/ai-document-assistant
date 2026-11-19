/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5104, proxy: { '/api': 'http://127.0.0.1:8104' } },
  preview: { port: 5104, proxy: { '/api': 'http://127.0.0.1:8104' } },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts', testTimeout: 30000 },
});
