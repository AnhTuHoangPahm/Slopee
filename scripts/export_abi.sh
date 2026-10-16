#!/usr/bin/env bash
# Xuất ABI đã đóng băng (M1) của SlopeeEscrowMaster và MockUSD.
#   ./scripts/export_abi.sh          ghi shared/abi/*.json (nguồn duy nhất cho backend) và chép sang frontend/src/lib/abi/
#   ./scripts/export_abi.sh --check  không ghi; thoát mã 1 nếu ABI đã commit lệch contract hiện tại (dùng trong CI)
# ABI được sinh bằng `forge inspect` rồi chuẩn hóa (indent 2, khóa giữ nguyên thứ tự) để diff ổn định.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
command -v forge >/dev/null || { echo "Cần Foundry (forge) trong PATH" >&2; exit 2; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cd "$ROOT/contracts"
for name in SlopeeEscrowMaster MockUSD; do
  forge inspect "$name" abi --json | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), indent=2, ensure_ascii=False))' > "$TMP/$name.json"
done

DEST_SHARED="$ROOT/shared/abi"
DEST_FRONT="$ROOT/frontend/src/lib/abi"
status=0
for name in SlopeeEscrowMaster MockUSD; do
  for dest in "$DEST_SHARED" "$DEST_FRONT"; do
    if [ "$CHECK" = 1 ]; then
      if ! cmp -s "$TMP/$name.json" "$dest/$name.json"; then
        echo "ABI lệch: $dest/$name.json (chạy ./scripts/export_abi.sh rồi commit)" >&2; status=1
      fi
    else
      mkdir -p "$dest"; cp "$TMP/$name.json" "$dest/$name.json"
    fi
  done
done
[ "$CHECK" = 1 ] && { [ $status = 0 ] && echo "ABI khớp contract." ; exit $status; }
echo "Đã xuất ABI -> shared/abi/ và frontend/src/lib/abi/"
