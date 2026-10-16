"""Kiểm tra chéo ngôn ngữ phía Python cho shared/eip712 (SDD 8.3, tuần 1 [Q]).

Cùng một tệp `vectors.json` được kiểm tra ở 3 nơi và phải cho kết quả giống hệt:
  * Python (tệp này, eth_account)        * JavaScript (frontend/src/__tests__/eip712Vectors.test.js, ethers v6)
  * Solidity (contracts/test/Eip712Vectors.t.sol, Foundry — còn nạp thật báo giá vào contract)
"""
import importlib.util
import json
from pathlib import Path

import pytest

eth_account = pytest.importorskip("eth_account")
from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402
from eth_utils import keccak  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TYPES = json.loads((ROOT / "shared/eip712/types.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "shared/eip712/vectors.json").read_text(encoding="utf-8"))


def _full_message(primary, message):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            primary: TYPES["types"][primary],
        },
        "primaryType": primary,
        "domain": VECTORS["domain"],
        # JSON mang uint256 dạng chuỗi thập phân (SDD 8.2) → đổi sang int cho eth_account
        "message": {
            f["name"]: int(message[f["name"]]) if f["type"].startswith("uint") else message[f["name"]]
            for f in TYPES["types"][primary]
        },
    }


def _check_vector(primary, v):
    signable = encode_typed_data(full_message=_full_message(primary, v["message"]))
    assert "0x" + signable.header.hex() == v["domainSeparator"]
    assert "0x" + signable.body.hex() == v["structHash"]
    digest = keccak(b"\x19\x01" + signable.header + signable.body)
    assert "0x" + digest.hex() == v["digest"]
    return signable


@pytest.mark.parametrize("v", VECTORS["orderQuote"], ids=lambda v: v["name"])
def test_order_quote_vector(v):
    signable = _check_vector("OrderQuote", v)
    assert Account.recover_message(signable, signature=v["signature"]) == v["signer"]
    assert v["signer"] == VECTORS["accounts"]["quoteSigner"]


@pytest.mark.parametrize("v", VECTORS["disputeResolution"], ids=lambda v: v["name"])
def test_dispute_resolution_vector(v):
    signable = _check_vector("DisputeResolution", v)
    assert Account.recover_message(signable, signature=v["signature"]) == v["signer"]
    assert Account.recover_message(signable, signature=v["arbitratorSignature"]) == v["arbitrator"]


def test_signatures_are_65_bytes_low_s_v27_28():
    """SDD 8.2: chữ ký 65 byte (r,s,v), v ∈ {27,28}, s thấp (OpenZeppelin ECDSA từ chối s cao)."""
    half_n = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
    sigs = [v["signature"] for v in VECTORS["orderQuote"]]
    for v in VECTORS["disputeResolution"]:
        sigs += [v["signature"], v["arbitratorSignature"]]
    for s in sigs:
        raw = bytes.fromhex(s[2:])
        assert len(raw) == 65
        assert raw[64] in (27, 28)
        assert int.from_bytes(raw[32:64], "big") <= half_n


def test_type_strings_match_field_lists():
    for name, fields in TYPES["types"].items():
        expected = f"{name}(" + ",".join(f"{f['type']} {f['name']}" for f in fields) + ")"
        assert TYPES["typeStrings"][name] == expected


@pytest.mark.parametrize("v", VECTORS["docHash"], ids=lambda v: v["name"])
def test_doc_hash_vector(v):
    spec = importlib.util.spec_from_file_location("gen_vectors", ROOT / "scripts/gen_eip712_vectors.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert gen.canonical_json(v["summary"]) == v["canonicalJson"]
    assert "0x" + keccak(v["canonicalJson"].encode("utf-8")).hex() == v["docHash"]


def test_doc_hash_rejects_floats_and_bools():
    spec = importlib.util.spec_from_file_location("gen_vectors", ROOT / "scripts/gen_eip712_vectors.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    with pytest.raises(ValueError):
        gen.canonical_json({"price_vnd": 1.5})
    with pytest.raises(ValueError):
        gen.canonical_json({"ok": True})


def test_vectors_file_is_up_to_date_with_generator():
    spec = importlib.util.spec_from_file_location("gen_vectors", ROOT / "scripts/gen_eip712_vectors.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert json.dumps(gen.build(), ensure_ascii=False, indent=2) + "\n" == (ROOT / "shared/eip712/vectors.json").read_text(encoding="utf-8")
