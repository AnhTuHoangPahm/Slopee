#!/usr/bin/env bash
# Sinh chứng chỉ HTTPS cho Vite dev server (frontend/certs/dev-{key,cert}.pem) để MetaMask chạy được trên máy khác
# trong LAN/VPN: trình duyệt chỉ bật window.ethereum ở secure context (https:// hoặc localhost), và MetaMask chỉ nhận
# RPC https ngoài loopback. Chạy MỘT lần; sau đó `npm run dev -- --port 5173 --strictPort` tự dùng HTTPS khi thấy tệp.
#
#   ./scripts/dev_cert.sh [IP-hoặc-tên-máy ...]     ví dụ: ./scripts/dev_cert.sh 100.101.102.103 25.1.2.3
#   ./scripts/dev_cert.sh --remove                  xóa chứng chỉ (quay lại http://localhost:5173)
#
# Thứ tự ưu tiên (tự chọn công cụ có sẵn):
#   1. Tailscale  : chứng chỉ Let's Encrypt THẬT cho <máy>.<tailnet>.ts.net — mọi thiết bị tin cậy sẵn, MetaMask nhận RPC.
#                   (bật "HTTPS Certificates" ở https://login.tailscale.com/admin/dns). Vào bằng https://<máy>.<tailnet>.ts.net:5173
#   2. mkcert     : CA cục bộ; thiết bị khác phải cài rootCA.pem (mkcert -CAROOT) mới tin cậy.
#   3. openssl    : tự ký — trình duyệt cảnh báo, MetaMask extension thường TỪ CHỐI RPC tự ký (dùng 1 hoặc 2 nếu cần ví).
# Hamachi / Radmin không cấp tên miền: dùng mkcert hoặc openssl với IP của adapter, hoặc đi đường Tailscale.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/frontend/certs"; KEY="$DIR/dev-key.pem"; CERT="$DIR/dev-cert.pem"
log() { printf '\033[1;34m[cert]\033[0m %s\n' "$*"; }

if [ "${1:-}" = "--remove" ]; then rm -f "$KEY" "$CERT"; log "Đã xóa chứng chỉ → dev server quay lại http."; exit 0; fi
mkdir -p "$DIR"; chmod 700 "$DIR" 2>/dev/null || true

# SAN: tên/IP truyền vào + IP của máy (nếu lấy được)
SANS=(localhost 127.0.0.1 ::1 "$@")
if command -v hostname >/dev/null 2>&1; then
  for ip in $(hostname -I 2>/dev/null || true); do SANS+=("$ip"); done
fi

if command -v tailscale >/dev/null 2>&1 && TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null)" && [ -n "$TS_NAME" ]; then
  log "Tailscale: xin chứng chỉ cho $TS_NAME"
  if tailscale cert --cert-file "$CERT" --key-file "$KEY" "$TS_NAME"; then
    log "Xong. Mở: https://$TS_NAME:5173  (cấp lại khi gần hết hạn ~90 ngày)"; chmod 600 "$KEY"; exit 0
  fi
  log "tailscale cert thất bại (đã bật HTTPS Certificates ở admin console chưa?) → thử công cụ khác"
fi

if command -v mkcert >/dev/null 2>&1; then
  log "mkcert: ${SANS[*]}"
  mkcert -install >/dev/null 2>&1 || true
  mkcert -key-file "$KEY" -cert-file "$CERT" "${SANS[@]}"
  log "Xong. Máy khác cần cài CA: $(mkcert -CAROOT)/rootCA.pem (iOS/Android: cài profile + bật tin cậy)."
  chmod 600 "$KEY"; exit 0
fi

command -v openssl >/dev/null 2>&1 || { echo "Cần một trong: tailscale, mkcert, openssl" >&2; exit 1; }
ALT=""; i=0
for s in "${SANS[@]}"; do
  i=$((i+1))
  if [[ "$s" =~ ^[0-9.]+$ || "$s" == *:* ]]; then ALT+="IP.$i = $s"$'\n'; else ALT+="DNS.$i = $s"$'\n'; fi
done
CNF="$(mktemp)"; trap 'rm -f "$CNF"' EXIT
cat >"$CNF" <<CNFEOF
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = slopee-dev
[v3]
subjectAltName = @alt
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
[alt]
$ALT
CNFEOF
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -keyout "$KEY" -out "$CERT" -config "$CNF" 2>/dev/null
chmod 600 "$KEY"
log "Đã tạo chứng chỉ TỰ KÝ (SAN: ${SANS[*]}). Trình duyệt sẽ cảnh báo; MetaMask extension có thể từ chối RPC tự ký → ưu tiên Tailscale/mkcert."
