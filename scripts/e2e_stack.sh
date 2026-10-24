#!/usr/bin/env bash
# Dựng / dọn stack cho E2E Web3 của Playwright (Tuần 8, C). Cần: Foundry, Python 3.12 (đã pip install backend/requirements.txt), MySQL đang chạy.
#   ./scripts/e2e_stack.sh up      Anvil sạch + deploy, DB + migration, gieo admin/shipper, chạy backend + Indexer + Scheduler
#   ./scripts/e2e_stack.sh seed    chỉ gieo tài khoản admin/shipper (idempotent)
#   ./scripts/e2e_stack.sh down    tắt backend/Indexer/Scheduler (Anvil: ./scripts/bootstrap.sh --fresh hoặc kill theo .anvil.pid)
# Rồi:  cd frontend && npx playwright test --project=web3-e2e      (Playwright tự bật Vite dev server)
# Biến: DB_HOST/DB_USER/DB_PASSWORD/DB_NAME, E2E_ADMIN_USER/E2E_ADMIN_PASSWORD, E2E_SHIPPER_USER/E2E_SHIPPER_PASSWORD, AUTO_RELEASE_SECONDS (mặc định 5).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/.e2e"; mkdir -p "$RUN"
export E2E_ADMIN_USER="${E2E_ADMIN_USER:-e2e_admin}" E2E_ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-E2eAdminPass#2026}"
export E2E_SHIPPER_USER="${E2E_SHIPPER_USER:-e2e_shipper}" E2E_SHIPPER_PASSWORD="${E2E_SHIPPER_PASSWORD:-E2eShipperPass#2026}"
export DB_NAME="${DB_NAME:-slopee_db}" SLOPEE_ENV="${SLOPEE_ENV:-test}" SECRET_KEY="${SECRET_KEY:-e2e-secret-key}"
# Quét/đối soát nhanh trong E2E (mặc định production là 60 giây)
export AUTO_RELEASE_SECONDS="${AUTO_RELEASE_SECONDS:-5}" QUOTE_SWEEP_SECONDS="${QUOTE_SWEEP_SECONDS:-10}" DISPUTE_SIG_EXPIRY_SECONDS="${DISPUTE_SIG_EXPIRY_SECONDS:-30}"
log() { printf '\033[1;34m[e2e]\033[0m %s\n' "$*"; }

seed() {
  ( cd "$ROOT/backend"
    ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" python3 -m flask --app app seed-admin --username "$E2E_ADMIN_USER" >/dev/null 2>&1 || log "admin đã có (hoặc không gieo được): bỏ qua"
    SHIPPER_PASSWORD="$E2E_SHIPPER_PASSWORD" python3 -m flask --app app seed-shipper --username "$E2E_SHIPPER_USER" >/dev/null 2>&1 || log "shipper đã có (hoặc không gieo được): bỏ qua" )
}

start() { # start <tên> <lệnh...>
  local name="$1"; shift
  ( cd "$ROOT/backend" && nohup "$@" >"$RUN/$name.log" 2>&1 & echo $! >"$RUN/$name.pid" )
}

wait_http() { # wait_http <url> <giây>
  for _ in $(seq 1 "$2"); do curl -fsS -o /dev/null "$1" 2>/dev/null && return 0; sleep 1; done
  echo "Hết giờ chờ $1 (xem $RUN/*.log)" >&2; return 1
}

case "${1:-}" in
  up)
    log "Anvil sạch + deploy contract"; "$ROOT/scripts/bootstrap.sh" --fresh --force-env
    log "CSDL + migration"; ( cd "$ROOT/backend" && python3 init_db.py && python3 migrate.py up )
    seed
    log "backend :5000, Indexer, Scheduler"
    start backend python3 -m flask --app app run --port 5000
    start indexer python3 -m slopee_web3.adapters.indexer
    start scheduler python3 -m slopee_web3.adapters.scheduler
    wait_http "http://localhost:5000/api/products/categories" 60
    log "Sẵn sàng. Log: $RUN/*.log (quét log: E2E_BACKEND_LOG=$RUN/backend.log)"
    ;;
  seed) seed ;;
  down)
    for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done
    log "Đã tắt backend/Indexer/Scheduler" ;;
  *) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
