import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://app:8010',
        changeOrigin: true
      },
      '/chat': {
        target: 'http://app:8010',
        changeOrigin: true
      },
      '/batch': {
        target: 'http://app:8010',
        changeOrigin: true
      },
      '/health': {
        target: 'http://app:8010',
        changeOrigin: true
      },
      '/result': {
        target: 'http://app:8010',
        changeOrigin: true
      }
    }
  }
})
