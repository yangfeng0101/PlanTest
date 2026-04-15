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
      '/api/v1/scripts': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/tasks': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/reports': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api/v1/statistics': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
      // WebSocket proxy for screen streaming (MJPEG/WebRTC)
      '/ws': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
