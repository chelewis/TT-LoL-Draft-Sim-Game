import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies API and WebSocket traffic to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  test: { environment: 'node' },
})
