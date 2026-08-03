import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// The API base is proxied in dev so the browser never deals with CORS, and read
// from VITE_API_URL in production builds.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.GYANTRA_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        // SSE needs buffering disabled to stream through the proxy.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            }
          })
        },
      },
    },
  },
  preview: { host: '0.0.0.0', port: 5173 },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 900 },
})
