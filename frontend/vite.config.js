import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dashboard is served from :3000 and proxies /api to the Flask backend on
// :5000, so the browser only ever talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.DASHBOARD_PORT) || 3300,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
