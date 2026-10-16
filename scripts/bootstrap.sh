#!/usr/bin/env bash
# Dựng môi trường Web3 cục bộ bằng MỘT lệnh (SDD 12.1, SRS mục 11 tuần 1):
#   kiểm công cụ → (cài thư viện contract) → Anvil --block-time 2 → forge build → triển khai MockUSD + Escrow
#   → ghi deployments/local.json → sinh backend/.env.web3 từ tài khoản Anvil → chép JSON cho frontend.
#
# Dùng:  ./scripts/bootstrap.sh [--no-anvil] [--fresh] [--force-env] [--help]
#   --no-anvil   không tự khởi động Anvil (dùng node đang chạy ở RPC_URL)
#   --fresh      tắt Anvil do script này đã bật trước đó rồi khởi động lại (chain sạch, mất mọi trạng thái)
#   --force-env  ghi đè backend/.env.web3 nếu đã tồn tại
#
# CHƯA làm ở tuần 1 (thêm dần theo kế hoạch): chạy migration MySQL Web3 (tuần 2), khởi động web/indexer/scheduler (tuần 3-5).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RPC_URL="${RPC_URL:-http://127.0.0.1:8545}"
RPC_HOST="${RPC_URL#*://}"; RPC_PORT="${RPC_HOST##*:}"; RPC_PORT="${RPC_PORT%%/*}"; RPC_HOST="${RPC_HOST%%:*}"
CHAIN_ID=31337
ANVIL_PID_FILE="$ROOT/.anvil.pid"
ANVIL_LOG="$ROOT/.anvil.log"
START_ANVIL=1; FRESH=0; FORCE_ENV=0

for arg in "$@"; do
  case "$arg" in
    --no-anvil) START_ANVIL=0 ;;
    --fresh) FRESH=1 ;;
    --force-env) FORCE_ENV=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap] CẢNH BÁO:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[bootstrap] LỖI:\033[0m %s\n' "$*" >&2; exit 1; }

# 1) Kiểm công cụ ------------------------------------------------------------
need() { command -v "$1" >/dev/null 2>&1 || die "Thiếu '$1'. $2"; }
need forge   "Cài Foundry: https://book.getfoundry.sh/getting-started/installation (foundryup)"
need anvil   "Đi kèm Foundry (foundryup)"
need cast    "Đi kèm Foundry (foundryup)"
need python3 "Cần Python 3.12+"
need node    "Cần Node 22+"
command -v mysql >/dev/null 2>&1 || warn "Không thấy 'mysql' trong PATH — tuần 1 chưa cần, nhưng migration tuần 2 sẽ cần MySQL 8.0.16+."

# 2) Thư viện contract (khóa phiên bản theo SRS 10.2) ---------------------------
if [ ! -d contracts/lib/forge-std/src ] || [ ! -d contracts/lib/openzeppelin-contracts/contracts ]; then
  log "Cài thư viện contract (forge-std v1.9.4, OpenZeppelin v5.0.2)…"
  ./scripts/install_contract_deps.sh
fi

# 3) Anvil -------------------------------------------------------------------
anvil_up() { cast chain-id --rpc-url "$RPC_URL" >/dev/null 2>&1; }

if [ "$FRESH" = 1 ] && [ -f "$ANVIL_PID_FILE" ]; then
  log "Tắt Anvil cũ (pid $(cat "$ANVIL_PID_FILE"))…"
  kill "$(cat "$ANVIL_PID_FILE")" 2>/dev/null || true
  rm -f "$ANVIL_PID_FILE"; sleep 1
fi

if anvil_up; then
  log "Anvil đã chạy tại $RPC_URL."
elif [ "$START_ANVIL" = 1 ]; then
  log "Khởi động Anvil (--block-time 2, chainId $CHAIN_ID)…"
  nohup anvil --host "$RPC_HOST" --port "$RPC_PORT" --block-time 2 --chain-id "$CHAIN_ID" >"$ANVIL_LOG" 2>&1 &
  echo $! >"$ANVIL_PID_FILE"
  for _ in $(seq 1 30); do anvil_up && break; sleep 0.5; done
  anvil_up || die "Anvil không khởi động được. Xem $ANVIL_LOG"
else
  die "Không kết nối được Anvil ở $RPC_URL (đã dùng --no-anvil)."
fi

[ "$(cast chain-id --rpc-url "$RPC_URL")" = "$CHAIN_ID" ] || die "chainId không phải $CHAIN_ID — chỉ hỗ trợ Anvil cục bộ."

# 4) Biên dịch + triển khai ----------------------------------------------------
mkdir -p deployments
log "forge build…"
( cd contracts && forge build )

log "Triển khai MockUSD + SlopeeEscrowMaster…"
( cd contracts && forge script script/Deploy.s.sol:Deploy --rpc-url "$RPC_URL" --broadcast --slow )

[ -s deployments/local.json ] || die "deployments/local.json không được tạo."

# 5) Kiểm tra kết quả: có mã trên chuỗi, đúng vai trò -------------------------------
read -r ESCROW USD DEPLOY_BLOCK < <(python3 - <<'PY'
import json
d = json.load(open("deployments/local.json", encoding="utf-8"))
print(d["escrow"], d["mockUSD"], d["deployBlock"])
PY
)
for addr in "$ESCROW" "$USD"; do
  [ "$(cast code "$addr" --rpc-url "$RPC_URL")" != "0x" ] || die "Không có mã contract tại $addr"
done
SHIPPER_ROLE="$(cast keccak "SHIPPER_ROLE")"
SHIPPER_ADDR="$(python3 -c 'import json;print(json.load(open("deployments/local.json"))["roles"]["shipper"])')"
[ "$(cast call "$ESCROW" 'hasRole(bytes32,address)(bool)' "$SHIPPER_ROLE" "$SHIPPER_ADDR" --rpc-url "$RPC_URL")" = "true" ] \
  || die "Shipper chưa được cấp SHIPPER_ROLE."
log "Escrow  : $ESCROW"
log "MockUSD : $USD"
log "deployBlock (chặn dưới): $DEPLOY_BLOCK → indexer_cursor.last_block khởi tạo = $((DEPLOY_BLOCK - 1))"

# 6) Chép cho frontend (Vite phục vụ từ public/) --------------------------------
mkdir -p frontend/public/deployments
cp deployments/local.json frontend/public/deployments/local.json

# 7) Sinh backend/.env.web3 từ tài khoản Anvil (4 khóa vai trò KHÁC NHAU) ----------------
# Khóa công khai của Anvil, CHỈ dùng cục bộ. Tệp bị .gitignore; không bao giờ dùng khóa này ở mạng thật.
ENV_FILE="backend/.env.web3"
if [ -f "$ENV_FILE" ] && [ "$FORCE_ENV" = 0 ]; then
  log "$ENV_FILE đã tồn tại — giữ nguyên (dùng --force-env để ghi đè)."
else
  cat >"$ENV_FILE" <<ENVEOF
# Sinh bởi scripts/bootstrap.sh — CHỈ cho Anvil cục bộ. Không commit. Không dùng khóa này ngoài môi trường thử.
RPC_URL=$RPC_URL
CHAIN_ID=$CHAIN_ID
ESCROW_ADDRESS=$ESCROW
MOCKUSD_ADDRESS=$USD
# Khóa vận hành của sàn (SRS 2.2): mỗi vai một khóa riêng
QUOTE_SIGNER_KEY=0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6
ARBITRATOR_KEY=0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
SHIPPER_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
# Tham số Indexer (tuần 3-4)
POLL_SECONDS=2
CONFIRMATIONS=0
REORG_DEPTH=0
INDEXER_START_BLOCK=$((DEPLOY_BLOCK - 1))
ENVEOF
  chmod 600 "$ENV_FILE"
  log "Đã ghi $ENV_FILE"
fi

log "XONG. Tài khoản thử: buyer 0x9965…A4dc (đã mint MockUSD), merchant 0x976E…0aa9."
log "Chưa tự chạy ở tuần 1: migration MySQL Web3, web/indexer/scheduler. Chạy backend + frontend thủ công như README."
