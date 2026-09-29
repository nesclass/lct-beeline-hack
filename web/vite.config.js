import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// сервер приложения — uvicorn app.main:app --port 8001 (8000 занят старым бэкендом)
const api = `http://127.0.0.1:${process.env.API_PORT || 8001}`;

export default defineConfig({
  plugins: [svelte()],
  server: { port: 5173, proxy: { '/api': api } },
  test: { include: ['src/**/*.test.js'], environment: 'node' },
});
