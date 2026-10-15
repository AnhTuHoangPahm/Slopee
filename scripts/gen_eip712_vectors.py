#!/usr/bin/env python3
"""Sinh shared/eip712/vectors.json (vector kiểm thử chéo ngôn ngữ, SDD 8.3).

Chạy lại:  python scripts/gen_eip712_vectors.py          (ghi tệp)
           python scripts/gen_eip712_vectors.py --check  (báo lỗi nếu tệp lệch, dùng cho CI)

Khóa dưới đây là KHÓA THỬ MẶC ĐỊNH CỦA ANVIL (công khai, không có giá trị). Chúng chỉ nằm trong script này;
vectors.json chỉ chứa địa chỉ và chữ ký, không chứa khóa. Chữ ký ECDSA của eth_account là tất định (RFC 6979).
"""
import argparse
import json
import sys
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
from eth_utils import keccak, to_checksum_address

ROOT = Path(__file__).resolve().parent.parent
TYPES_PATH = ROOT / "shared" / "eip712" / "types.json"
OUT_PATH = ROOT / "shared" / "eip712" / "vectors.json"

CHAIN_ID = 31337
VERIFYING_CONTRACT = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"  # = địa chỉ Escrow mà bootstrap.sh triển khai trên Anvil sạch (deployer #0, nonce 1)
ZERO = "0x0000000000000000000000000000000000000000"
FAR_FUTURE = 4102444800  # 2100-01-01T00:00:00Z

# Tài khoản Anvil mặc định (chỉ dùng cục bộ)
ANVIL_KEYS = {
    "arbitrator": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",   # account #2
    "quoteSigner": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",  # account #3
    "buyer": "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",        # account #5
    "merchant": "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",     # account #6
}
ACCOUNTS = {name: Account.from_key(key) for name, key in ANVIL_KEYS.items()}
ADDR = {name: acct.address for name, acct in ACCOUNTS.items()}
MOCKUSD = to_checksum_address("0x5fbdb2315678afecb367f032d93f642f64180aa3")  # = MockUSD của bootstrap.sh (deployer #0, nonce 0)


def canonical_json(obj) -> str:
    """Chuẩn hóa theo SDD 5.3c: khóa tăng dần, không khoảng trắng thừa, UTF-8, chỉ số nguyên."""
    def check(o):
        if isinstance(o, bool) or isinstance(o, float):
            raise ValueError("canonical_json chỉ nhận số nguyên, không nhận float/bool")
        if isinstance(o, dict):
            for v in o.values():
                check(v)
        elif isinstance(o, list):
            for v in o:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def doc_hash(summary) -> str:
    return "0x" + keccak(canonical_json(summary).encode("utf-8")).hex()


def typed(types, primary, message):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            primary: types[primary],
        },
        "primaryType": primary,
        "domain": {
            "name": "SlopeeEscrow",
            "version": "1",
            "chainId": CHAIN_ID,
            "verifyingContract": VERIFYING_CONTRACT,
        },
        "message": message,
    }


def digest_parts(full):
    signable = encode_typed_data(full_message=full)
    domain_sep = signable.header
    struct_hash = signable.body
    digest = keccak(b"\x19\x01" + domain_sep + struct_hash)
    return "0x" + domain_sep.hex(), "0x" + struct_hash.hex(), digest


def sign(full, who):
    signed = ACCOUNTS[who].sign_message(encode_typed_data(full_message=full))
    sig = signed.signature.hex()
    return sig if sig.startswith("0x") else "0x" + sig


def link_message(domain, address, user_id, nonce, chain_id, issued_at, expires_at):
    """Thông điệp liên kết ví UC-00 (SDD 5.3g). Bản dựng ĐỘC LẬP với backend/slopee_web3/domain/wallet.py:
    hai nơi phải cho cùng từng byte (test_w3_domain.py kiểm), nếu một bên đổi định dạng thì CI đỏ."""
    from datetime import datetime, timezone
    iso = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    return (f"{domain} wants you to link your wallet to a Slopee account.\n\n"
            f"Address: {address.lower()}\nAccount: {user_id}\nNonce: {nonce}\nChain ID: {chain_id}\n"
            f"Issued At: {iso(issued_at)}\nExpiration Time: {iso(expires_at)}")


def personal_sign(message, who):
    signed = ACCOUNTS[who].sign_message(encode_defunct(text=message))
    sig = signed.signature.hex()
    return sig if sig.startswith("0x") else "0x" + sig


def message_as_json(msg):
    """uint256 -> chuỗi thập phân (SDD 8.2); địa chỉ giữ dạng checksum."""
    return {k: (str(v) if isinstance(v, int) else v) for k, v in msg.items()}


def build():
    types = json.loads(TYPES_PATH.read_text(encoding="utf-8"))["types"]
    vectors = {
        "$comment": "SINH TỰ ĐỘNG bởi scripts/gen_eip712_vectors.py — không sửa tay. Python, JS và Solidity phải cho cùng domainSeparator/structHash/digest và chữ ký này.",
        "version": 1,
        "domain": {
            "name": "SlopeeEscrow",
            "version": "1",
            "chainId": CHAIN_ID,
            "verifyingContract": VERIFYING_CONTRACT,
        },
        "accounts": {name: addr for name, addr in ADDR.items()},
        "orderQuote": [],
        "disputeResolution": [],
        "docHash": [],
        "walletLink": [],
    }

    summary1 = {
        "order_code": "SLP-20261011-0001",
        "items": [
            {"product_id": "a1b2c3d4-0001", "quantity": 2, "unit_price_vnd": 150000},
            {"product_id": "a1b2c3d4-0002", "quantity": 1, "unit_price_vnd": 99000},
        ],
        "price_vnd": 399000,
        "created_at": 1791676800,
    }
    summary2 = {
        "price_vnd": 25000,
        "items": [{"quantity": 1, "unit_price_vnd": 25000, "product_id": "Áo thun — size M"}],
        "created_at": 1791676801,
        "order_code": "SLP-20261011-0002",
    }  # thứ tự khóa đảo + ký tự Unicode: kiểm tra chuẩn hóa sắp khóa và UTF-8
    h1, h2 = doc_hash(summary1), doc_hash(summary2)

    quote_msgs = [
        ("token-MockUSD", {
            "orderId": 1001, "buyer": ADDR["buyer"], "merchant": ADDR["merchant"], "token": MOCKUSD,
            "amount": 16_500_000, "inspectionDuration": 3 * 86400, "disputeTimeout": 14 * 86400,
            "feeBps": 300, "docHash": h1, "deadline": FAR_FUTURE,
        }),
        ("eth-zero-fee", {
            "orderId": 1002, "buyer": ADDR["buyer"], "merchant": ADDR["merchant"], "token": ZERO,
            "amount": 10**18, "inspectionDuration": 3600, "disputeTimeout": 7 * 86400,
            "feeBps": 0, "docHash": h2, "deadline": FAR_FUTURE,
        }),
        ("uint256-large-orderId", {
            "orderId": 2**53 + 12345, "buyer": ADDR["buyer"], "merchant": ADDR["merchant"], "token": MOCKUSD,
            "amount": 2**200 + 7, "inspectionDuration": 30 * 86400, "disputeTimeout": 90 * 86400,
            "feeBps": 1000, "docHash": "0x" + "ab" * 32, "deadline": FAR_FUTURE,
        }),
    ]
    for name, msg in quote_msgs:
        full = typed(types, "OrderQuote", msg)
        dom, struct, digest = digest_parts(full)
        vectors["orderQuote"].append({
            "name": name,
            "message": message_as_json(msg),
            "domainSeparator": dom,
            "structHash": struct,
            "digest": "0x" + digest.hex(),
            "signer": ADDR["quoteSigner"],
            "signature": sign(full, "quoteSigner"),
        })

    dispute_msgs = [
        ("payout-merchant", "buyer", {
            "orderId": 1001, "payoutTo": ADDR["merchant"], "amount": 16_500_000, "nonce": 0, "deadline": FAR_FUTURE,
        }),
        ("refund-buyer-nonce-3", "merchant", {
            "orderId": 1001, "payoutTo": ADDR["buyer"], "amount": 16_500_000, "nonce": 3, "deadline": FAR_FUTURE - 1,
        }),
    ]
    for name, who, msg in dispute_msgs:
        full = typed(types, "DisputeResolution", msg)
        dom, struct, digest = digest_parts(full)
        vectors["disputeResolution"].append({
            "name": name,
            "message": message_as_json(msg),
            "domainSeparator": dom,
            "structHash": struct,
            "digest": "0x" + digest.hex(),
            "signer": ADDR[who],
            "signature": sign(full, who),
        })
        # chữ ký của Trọng tài cho cùng thông điệp (đủ 2/3 khi ghép với Buyer/Merchant)
        vectors["disputeResolution"][-1]["arbitratorSignature"] = sign(full, "arbitrator")
        vectors["disputeResolution"][-1]["arbitrator"] = ADDR["arbitrator"]

    vectors["docHash"] = [
        {"name": "two-items", "summary": summary1, "canonicalJson": canonical_json(summary1), "docHash": h1},
        {"name": "key-order-and-unicode", "summary": summary2, "canonicalJson": canonical_json(summary2), "docHash": h2},
    ]
    link_args = {"domain": "localhost:5173", "address": ADDR["buyer"], "user_id": "3f2c9a52-6d0e-4b8e-9a51-0c1d2e3f4a5b",
                 "nonce": "0123456789abcdef0123456789abcdef", "chain_id": CHAIN_ID,
                 "issued_at": 1791676800, "expires_at": 1791677100}
    msg = link_message(**link_args)
    vectors["walletLink"] = [{
        "name": "buyer-link", "domain": link_args["domain"], "address": link_args["address"], "userId": link_args["user_id"],
        "nonce": link_args["nonce"], "chainId": CHAIN_ID, "issuedAt": link_args["issued_at"], "expiresAt": link_args["expires_at"],
        "message": msg, "signer": ADDR["buyer"], "signature": personal_sign(msg, "buyer"),
    }]
    return vectors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="chỉ so sánh với tệp hiện có")
    args = ap.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != text:
            print("vectors.json lệch so với script; chạy lại scripts/gen_eip712_vectors.py", file=sys.stderr)
            return 1
        print("vectors.json khớp")
        return 0
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"đã ghi {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
