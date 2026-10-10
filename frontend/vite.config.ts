import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // MapLibre 6 loads its worker from a file next to its main module; Vite's
  // dependency pre-bundling would move the module and break that path.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
