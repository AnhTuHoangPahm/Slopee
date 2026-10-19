import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { installWeb3Mock } from './mocks/web3Mock'
import { installDisputeMock } from './mocks/disputeMock'

// Tuần 1-3: dựng giao diện Web3 trên API giả khi chưa có Backend/chuỗi (SDD 9.6). Tắt khi chạy thật.
if (import.meta.env.VITE_WEB3_MOCK === 'true') {
  installWeb3Mock()
  // Tuần 6: màn hình ký phán quyết (/disputes/mock-dispute-1); đề xuất do `mock.state.propose()` hoặc bấm nút trong console của trình duyệt
  const dispute = installDisputeMock()
  dispute.state.propose({ payoutTo: 'buyer' })
  window.__disputeMock = dispute.state
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
