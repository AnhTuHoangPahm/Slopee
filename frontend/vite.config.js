import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // lib/eip712.js đọc ../shared/eip712/types.json (ngoài thư mục frontend/)
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    exclude: ['tests/**', 'node_modules/**', 'dist/**'],
  }
})
