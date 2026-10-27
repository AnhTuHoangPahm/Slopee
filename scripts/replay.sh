#!/usr/bin/env bash
# Replay Indexer từ block N rồi đối soát số dư (AC-08, AC-10, SDD 6.3). Tuần 9, B.
#
#   ./scripts/replay.sh                       # replay từ block 0 (hỏi xác nhận), so ảnh trước/sau, đối soát
#   ./scripts/replay.sh --yes                 # không hỏi (cron/CI/demo)
#   ./scripts/replay.sh --dry-run             # chỉ báo sẽ xóa/đặt lại những gì, không sửa gì
#   ./scripts/replay.sh --from-block 120 --yes   # replay từng phần từ block 120
#   ./scripts/replay.sh --report out.json     # biên bản JSON (mặc định .replay/replay-<giờ>.json)
#
# Tùy chọn:  --from-block N | --yes | --dry-run | --no-reconcile | --allow-scheduler | --report FILE | -h
#
# Việc script làm (xem backend/slopee_web3/adapters/indexer/replay.py):
#   1. kiểm tiền điều kiện: có backend/.env.web3; KHÔNG có Indexer khác đang chạy; Scheduler đang chạy thì dừng lại (xem dưới)
#   2. Indexer bắt kịp chuỗi, chụp ảnh các bảng dẫn xuất (đơn, tồn kho, sổ chờ rút, thông báo, đề xuất phán quyết, chain_events)
#   3. xóa dữ liệu dẫn xuất từ block N, dựng lại bằng chính handler của Indexer tới ĐÚNG block đã chụp, chụp lại và so khớp từng dòng
#   4. bật Indexer nền cho kịp chuỗi rồi chạy `scripts/reconcile.py --deep --events --wait 30` (số dư contract == tổng đơn mở + sổ chờ rút,
#      từng đơn khớp trạng thái contract), xong tắt Indexer nền
#
# Mã thoát:  0 = dựng lại khớp 100% và đối soát khớp  |  1 = khác ảnh trước, hoặc đối soát lệch  |  2 = không chạy được
#
# LƯU Ý: dừng Indexer (./scripts/e2e_stack.sh down hoặc kill tiến trình) trước khi chạy; dừng cả Scheduler để không có giao dịch mới trong lúc
# replay (muốn bỏ qua kiểm tra này: --allow-scheduler). Đừng replay giữa lúc có người đang mua: replay xử lại OrderCreated nên sẽ xóa món cùng
# sản phẩm mà Buyer vừa thêm lại vào giỏ sau khi đơn đó ký quỹ; thông báo do Indexer sinh cũng mất dấu "đã đọc".
# Anvil bị khởi động lại (SDD 15): chạy ./scripts/bootstrap.sh --fresh trước, rồi script này; bước so sánh trước/sau tự bỏ qua vì chuỗi đã bị thay.
# Biến môi trường: PYTHON (mặc định python3), DB_HOST/DB_USER/DB_PASSWORD/DB_NAME như backend.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
FROM=0; YES=""; DRY=""; RECONCILE=1; ALLOW_SCHED=0; REPORT=""

log()  { printf '\033[1;34m[replay]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[replay]\033[0m %s\n' "$*" >&2; exit 2; }
usage() { sed -n '2,/^set -uo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --from-block) [ $# -ge 2 ] || fail "--from-block cần một số"; FROM="$2"; shift 2 ;;
    --from-block=*) FROM="${1#*=}"; shift ;;
    --yes|-y) YES="--yes"; shift ;;
    --dry-run) DRY="--dry-run"; shift ;;
    --no-reconcile) RECONCILE=0; shift ;;
    --allow-scheduler) ALLOW_SCHED=1; shift ;;
    --report) [ $# -ge 2 ] || fail "--report cần tên tệp"; REPORT="$2"; shift 2 ;;
    --report=*) REPORT="${1#*=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Tùy chọn lạ: $1 (xem ./scripts/replay.sh --help)" ;;
  esac
done
case "$FROM" in ''|*[!0-9]*) fail "--from-block phải là số nguyên >= 0 (nhận: '$FROM')" ;; esac

# --- 1. tiền điều kiện
command -v "$PYTHON" >/dev/null 2>&1 || fail "Không tìm thấy $PYTHON (đặt biến PYTHON)."
[ -f "$ROOT/backend/.env.web3" ] || fail "Chưa có backend/.env.web3: chạy ./scripts/bootstrap.sh trước."
if command -v pgrep >/dev/null 2>&1; then
  if pgrep -f "slopee_web3[.]adapters[.]indexer" >/dev/null 2>&1; then
    fail "Đang có Indexer chạy: tắt nó rồi chạy lại (./scripts/e2e_stack.sh down). Replay giữ khóa Indexer nên không chạy chung được."
  fi
  if [ "$ALLOW_SCHED" -ne 1 ] && pgrep -f "slopee_web3[.]adapters[.]scheduler" >/dev/null 2>&1; then
    fail "Đang có Scheduler chạy (AutoRelease có thể gửi giao dịch giữa lúc replay): tắt nó, hoặc thêm --allow-scheduler nếu chắc chắn."
  fi
fi
if [ -z "$REPORT" ] && [ -z "$DRY" ]; then
  mkdir -p "$ROOT/.replay"; REPORT="$ROOT/.replay/replay-$(date +%Y%m%d-%H%M%S).json"
fi

# --- 2-3. replay + so ảnh trước/sau
ARGS=(--from-block "$FROM" --reset)
[ -n "$YES" ] && ARGS+=("$YES")
[ -n "$DRY" ] && ARGS+=("$DRY")
[ -n "$REPORT" ] && ARGS+=(--report "$REPORT")
log "Replay Indexer từ block $FROM${DRY:+ (dry-run)}"
( cd "$ROOT/backend" && "$PYTHON" -m slopee_web3.adapters.indexer "${ARGS[@]}" )
REPLAY_RC=$?

# --- 4. đối soát số dư (chỉ khi replay đã dựng lại xong và thật sự ghi dữ liệu)
RECON_RC=0
if [ "$REPLAY_RC" -eq 0 ] && [ -z "$DRY" ] && [ "$RECONCILE" -eq 1 ]; then
  log "Đối soát số dư sau replay"
  # Anvil vẫn đào block rỗng nên không có Indexer theo sau thì lag luôn >= 1 và `--deep` bỏ qua so từng đơn (chỉ so khi lag = 0):
  # bật Indexer nền (khóa đã nhả sau replay) trong lúc đối soát, rồi tắt.
  mkdir -p "$ROOT/.replay"
  ( cd "$ROOT/backend" && exec "$PYTHON" -m slopee_web3.adapters.indexer >"$ROOT/.replay/follow.log" 2>&1 ) &
  FOLLOW_PID=$!
  trap '[ -n "${FOLLOW_PID:-}" ] && kill "$FOLLOW_PID" 2>/dev/null' EXIT
  "$PYTHON" "$ROOT/scripts/reconcile.py" --deep --events --wait 30
  RECON_RC=$?
  kill "$FOLLOW_PID" 2>/dev/null; wait "$FOLLOW_PID" 2>/dev/null; FOLLOW_PID=""
fi

# --- kết luận: 2 (không chạy được) thắng 1 (khác/lệch) thắng 0
RC=0
for c in "$REPLAY_RC" "$RECON_RC"; do
  if [ "$c" -eq 2 ] || { [ "$c" -ne 0 ] && [ "$c" -ne 1 ]; }; then RC=2; break; fi
  [ "$c" -eq 1 ] && RC=1
done
case "$RC" in
  0) if [ -n "$DRY" ]; then log "DRY-RUN xong, không sửa gì."
     else
       MSG="ĐẠT: dựng lại khớp 100% với ảnh trước replay"
       [ "$RECONCILE" -eq 1 ] && MSG="$MSG, đối soát số dư khớp"
       [ -n "$REPORT" ] && MSG="$MSG. Biên bản: $REPORT"
       log "$MSG"
     fi ;;
  1) log "KHÔNG ĐẠT: trạng thái dựng lại KHÁC ảnh trước replay hoặc số dư lệch (xem chi tiết ở trên).${REPORT:+ Biên bản: $REPORT}" >&2 ;;
  *) log "KHÔNG CHẠY ĐƯỢC (mã $REPLAY_RC/$RECON_RC): xem thông báo ở trên." >&2; RC=2 ;;
esac
exit "$RC"
