#!/usr/bin/env bash
# Dựng / dọn stack cho E2E Web3 của Playwright (Tuần 8, C). Cần: Foundry, Python 3.12 (đã pip install backend/requirements.txt), MySQL đang chạy.
#   ./scripts/e2e_stack.sh up      Anvil sạch + deploy, DB + migration, gieo admin/shipper, chạy backend + Indexer + Scheduler
#   ./scripts/e2e_stack.sh seed    chỉ gieo tài khoản admin/shipper (idempotent)
#   RESET_DB=1 ./scripts/e2e_stack.sh up   như `up` nhưng XÓA CSDL $DB_NAME trước (chỉ nhận tên bắt đầu bằng "slopee"): cần khi chuỗi bị dựng lại mà CSDL còn đơn/con trỏ Indexer cũ
#   ./scripts/e2e_stack.sh down    tắt backend/Indexer/Scheduler (Anvil: ./scripts/bootstrap.sh --fresh hoặc kill theo .anvil.pid)
# Rồi:  cd frontend && npx playwright test --project=web3-e2e      (Playwright tự bật Vite dev server)
# Mạng: CHỈ cổng 5173 (Vite) cần mở cho LAN/VPN. Backend :5000, Anvil :8545 và MySQL :3306 chỉ nghe 127.0.0.1;
#       máy khác đi qua proxy cùng origin của Vite (/api, /rpc đã lọc). Chạy ./scripts/dev_cert.sh một lần để có HTTPS cho MetaMask từ xa.
#       REQUIRE_DB_LOOPBACK=1 → dừng nếu MySQL đang nghe ngoài loopback (mặc định chỉ cảnh báo).
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

# MySQL KHÔNG được nghe ngoài loopback (mặc định MySQL 8 nghe "*" trên Windows/Linux). Script không tự sửa được cấu hình
# mysqld (cần quyền quản trị + khởi động lại) nên kiểm tra và hướng dẫn; REQUIRE_DB_LOOPBACK=1 để biến cảnh báo thành lỗi.
check_db_exposure() {
  case "${DB_HOST:-localhost}" in localhost|127.0.0.1|::1) ;; *) log "DB_HOST=${DB_HOST} là máy khác: bỏ qua kiểm tra bind-address"; return 0 ;; esac
  local rc=0
  ( cd "$ROOT/backend" && python3 - <<'PY'
import os, sys, pymysql
LOOP = {'127.0.0.1', '::1', 'localhost'}
try:
    c = pymysql.connect(host=os.environ.get('DB_HOST', 'localhost'), user=os.environ.get('DB_USER', 'root'), password=os.environ.get('DB_PASSWORD', ''))
except Exception as e:  # không kết nối được thì các bước sau tự báo lỗi rõ hơn
    print(f'(không kiểm tra được bind-address: {e})'); sys.exit(0)
cur = c.cursor()
def var(name):
    try:
        cur.execute('SELECT @@GLOBAL.' + name); return cur.fetchone()[0]
    except Exception:
        return None
if var('skip_networking') in (1, '1', 'ON'):
    print('MySQL: skip_networking=ON (chỉ socket/pipe cục bộ) — an toàn'); sys.exit(0)
bad = []
for name in ('bind_address', 'mysqlx_bind_address'):
    v = var(name)
    if v is None: continue
    if any(p.strip().split(':')[0] not in LOOP and p.strip() not in LOOP for p in str(v).split(',')):
        bad.append(f'{name}={v}')
if bad:
    print('MYSQL ĐANG NGHE NGOÀI LOOPBACK: ' + ', '.join(bad) + f' (cổng {var("port")})')
    sys.exit(3)
print('MySQL chỉ nghe loopback — an toàn')
PY
  ) || rc=$?
  if [ "$rc" = 3 ]; then
    cat >&2 <<'MSG'
[e2e] CẢNH BÁO: MySQL đang mở cổng cho mạng ngoài. Đóng lại (cần quyền admin, sau đó khởi động lại MySQL):
        my.ini (Windows, %ProgramData%\MySQL\MySQL Server 8.x\) hoặc my.cnf (Linux), mục [mysqld]:
            bind-address = 127.0.0.1
            mysqlx-bind-address = 127.0.0.1
        (hoặc skip-networking nếu chỉ dùng socket/named pipe). Kiểm tra: mysql -e "SELECT @@bind_address".
      Thêm: tường lửa chặn inbound TCP 3306/33060, và không có tài khoản host '%' (SELECT user,host FROM mysql.user).
MSG
    if [ "${REQUIRE_DB_LOOPBACK:-0}" = 1 ]; then echo "REQUIRE_DB_LOOPBACK=1 → dừng." >&2; exit 4; fi
  elif [ "$rc" != 0 ]; then
    return "$rc"
  fi
  return 0   # cảnh báo không phải lỗi: không để set -e của script gọi thoát
}

reset_db() { # xóa CSDL cũ để khớp với chuỗi Anvil vừa dựng lại (Indexer/đơn cũ trỏ vào block không còn tồn tại)
  case "$DB_NAME" in slopee*) ;; *) echo "RESET_DB chỉ xóa CSDL có tên bắt đầu bằng 'slopee' (đang là '$DB_NAME')" >&2; exit 2 ;; esac
  log "Xóa CSDL $DB_NAME"
  ( cd "$ROOT/backend" && python3 - <<'PY'
import os, pymysql
c = pymysql.connect(host=os.environ.get('DB_HOST', 'localhost'), user=os.environ.get('DB_USER', 'root'), password=os.environ.get('DB_PASSWORD', ''))
c.cursor().execute('DROP DATABASE IF EXISTS `%s`' % os.environ['DB_NAME'])
c.close()
PY
  )
}

case "${1:-}" in
  up)
    check_db_exposure
    case "${RPC_URL:-http://127.0.0.1:8545}" in http://127.0.0.1:*|http://localhost:*) ;; *) log "CẢNH BÁO: RPC_URL=${RPC_URL} không phải loopback — Anvil mở khóa sẵn tài khoản công khai, đừng để lộ ra mạng." ;; esac
    log "Anvil sạch + deploy contract"; "$ROOT/scripts/bootstrap.sh" --fresh --force-env
    if [ "${RESET_DB:-0}" = 1 ]; then reset_db; fi
    log "CSDL + migration"; ( cd "$ROOT/backend" && python3 init_db.py && python3 migrate.py up )
    seed
    log "backend :5000, Indexer, Scheduler"
    start backend python3 -m flask --app app run --host 127.0.0.1 --port 5000
    start indexer python3 -m slopee_web3.adapters.indexer
    start scheduler python3 -m slopee_web3.adapters.scheduler
    wait_http "http://localhost:5000/api/products/categories" 60
    log "Sẵn sàng. Log: $RUN/*.log (quét log: E2E_BACKEND_LOG=$RUN/backend.log)"
    log "Tiếp theo: (cd frontend && npm run dev -- --port 5173 --strictPort). Máy chủ: localhost:5173; máy khác: <IP-VPN>:5173"
    if [ -f "$ROOT/frontend/certs/dev-cert.pem" ]; then log "Có frontend/certs → Vite chạy HTTPS (https://...:5173), MetaMask dùng được từ xa."
    else log "Chưa có HTTPS: máy khác vào được web nhưng KHÔNG dùng được MetaMask. Chạy ./scripts/dev_cert.sh <IP-VPN> một lần."; fi
    ;;
  seed) seed ;;
  down)
    for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done
    log "Đã tắt backend/Indexer/Scheduler" ;;
  *) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
