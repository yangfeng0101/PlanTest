import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api/v1/auth': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/users': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/scripts': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/schedules': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/tasks': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/reports': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/api/v1/statistics': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/api/v1/alerts': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/api/v1/export': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
      // Legacy WebSocket proxy for services that still expose WS endpoints.
      '/ws': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
