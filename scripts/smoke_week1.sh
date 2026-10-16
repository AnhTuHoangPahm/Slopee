#!/usr/bin/env bash
# Smoke test tuần 1 trên Anvil THẬT (sau ./scripts/bootstrap.sh): báo giá do Python ký (shared/eip712/vectors.json)
# → Buyer approve + depositEscrow → Shipper confirmDelivery → Buyer earlyRelease → kiểm số dư Merchant/phí/escrow.
# Chứng minh chuỗi Python-ký → contract-chấp nhận → giải ngân đúng phí chạy được trên node thật, không chỉ trong forge test.
# Chỉ chạy được trên Anvil sạch vừa bootstrap (địa chỉ contract trong vector = địa chỉ bootstrap triển khai; orderId 1001 chưa dùng).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
RPC_URL="${RPC_URL:-http://127.0.0.1:8545}"
BUYER_KEY=0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba   # Anvil #5 (công khai)
SHIPPER_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d # Anvil #1 (công khai)
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

eval "$(python3 - <<'PY'
import json
d = json.load(open("deployments/local.json", encoding="utf-8"))
v = json.load(open("shared/eip712/vectors.json", encoding="utf-8"))
q = v["orderQuote"][0]; m = q["message"]
assert d["escrow"].lower() == v["domain"]["verifyingContract"].lower(), "địa chỉ escrow khác vector — cần Anvil sạch + bootstrap.sh (hoặc chạy lại scripts/gen_eip712_vectors.py)"
print(f'ESC={d["escrow"]}; USD={d["mockUSD"]}; BUYER={m["buyer"]}; MERCHANT={m["merchant"]}; FEE_TO={d["roles"]["feeRecipient"]}')
print(f'ORDER_ID={m["orderId"]}; AMOUNT={m["amount"]}; FEE_BPS={m["feeBps"]}; SIG={q["signature"]}')
print("QUOTE='(" + ",".join(m[k] for k in ["orderId","buyer","merchant","token","amount","inspectionDuration","disputeTimeout","feeBps","docHash","deadline"]) + ")'")
PY
)"
Q_SIG='(uint256,address,address,address,uint256,uint256,uint256,uint256,bytes32,uint256)'

bal() { cast call "$USD" 'balanceOf(address)(uint256)' "$1" --rpc-url "$RPC_URL" | awk '{print $1}'; }
state() { cast call "$ESC" 'orders(uint256)(address,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint8,bytes32)' "$ORDER_ID" --rpc-url "$RPC_URL" | sed -n '11p' | awk '{print $1}'; }

M0=$(bal "$MERCHANT"); F0=$(bal "$FEE_TO")
cast send "$USD" 'approve(address,uint256)' "$ESC" "$AMOUNT" --private-key "$BUYER_KEY" --rpc-url "$RPC_URL" >/dev/null
cast send "$ESC" "depositEscrow($Q_SIG,bytes)" "$QUOTE" "$SIG" --private-key "$BUYER_KEY" --rpc-url "$RPC_URL" >/dev/null
[ "$(state)" = "1" ] || fail "đơn không ở LOCKED sau khi nạp (state=$(state))"
[ "$(bal "$ESC")" = "$AMOUNT" ] || fail "số dư escrow != amount"

cast send "$ESC" 'confirmDelivery(uint256)' "$ORDER_ID" --private-key "$SHIPPER_KEY" --rpc-url "$RPC_URL" >/dev/null
[ "$(state)" = "2" ] || fail "đơn không ở DELIVERED"
cast send "$ESC" 'earlyRelease(uint256)' "$ORDER_ID" --private-key "$BUYER_KEY" --rpc-url "$RPC_URL" >/dev/null
[ "$(state)" = "4" ] || fail "đơn không ở COMPLETED"

FEE=$(( AMOUNT * FEE_BPS / 10000 ))
[ "$(( $(bal "$MERCHANT") - M0 ))" = "$(( AMOUNT - FEE ))" ] || fail "tiền Merchant sai"
[ "$(( $(bal "$FEE_TO") - F0 ))" = "$FEE" ] || fail "tiền phí sai"
[ "$(bal "$ESC")" = "0" ] || fail "escrow còn dư tiền"
echo "SMOKE OK: đơn $ORDER_ID LOCKED → DELIVERED → COMPLETED; Merchant +$(( AMOUNT - FEE )), phí +$FEE, escrow = 0."
