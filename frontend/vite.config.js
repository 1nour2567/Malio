import { defineConfig } from 'vite'

// Malio PWA frontend — vanilla HTML5, zero framework
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8007',
        changeOrigin: true,
        secure: false,
        ws: true
      },
      '/stream': {
        target: 'http://localhost:8007',
        ws: true,
        changeOrigin: true
      },
      '/audio': {
        target: 'http://localhost:8007',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true
  },
  publicDir: 'public'
})
