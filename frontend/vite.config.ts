import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The frontend reaches the backend through VITE_API_URL (see src/api/config.ts), not a dev proxy.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { environment: 'node' },
})
