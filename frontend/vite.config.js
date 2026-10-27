import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { rpcGuardPlugin } from './vite.rpc-guard.js'

const here = path.dirname(fileURLToPath(import.meta.url))

// HTTPS (bắt buộc để MetaMask/window.ethereum hoạt động trên máy khác: trình duyệt chỉ bật ví ở "secure context").
// Tự bật khi có chứng chỉ do `scripts/dev_cert.sh` sinh ở frontend/certs/ (hoặc VITE_HTTPS_KEY/VITE_HTTPS_CERT).
// Ép tắt: VITE_HTTPS=0 (Playwright dùng).
function loadHttps() {
  if (process.env.VITE_HTTPS === '0') return undefined
  const key = process.env.VITE_HTTPS_KEY || path.join(here, 'certs', 'dev-key.pem')
  const cert = process.env.VITE_HTTPS_CERT || path.join(here, 'certs', 'dev-cert.pem')
  if (fs.existsSync(key) && fs.existsSync(cert)) return { key: fs.readFileSync(key), cert: fs.readFileSync(cert) }
  return undefined
}

// Chỉ cổng Vite (5173) lộ ra mạng; backend (5000) và Anvil (8545) chỉ nghe 127.0.0.1 và đi qua proxy cùng origin:
//   /api -> Flask      /rpc -> Anvil (đã lọc phương thức, xem vite.rpc-guard.js)
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:5000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), rpcGuardPlugin()],
  server: {
    // Cho phép thiết bị khác trong LAN/VPN (Tailscale, Hamachi, Radmin...) truy cập: listen 0.0.0.0
    host: true,
    port: 5173,
    https: loadHttps(),
    proxy: { '/api': { target: BACKEND, changeOrigin: false } },
    // lib/eip712.js đọc ../shared/eip712/types.json (ngoài thư mục frontend/)
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    exclude: ['tests/**', 'node_modules/**', 'dist/**'],
  }
})
