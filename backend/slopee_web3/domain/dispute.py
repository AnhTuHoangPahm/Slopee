"""Phán quyết tranh chấp (SRS 6, UC-06, BR-04). Thuần: kiểu dữ liệu, chọn cặp chữ ký, kiểm hạn. Không ký, không I/O.

Contract `resolveDispute` chỉ cần HAI chữ ký của HAI bên KHÁC NHAU trong {Buyer, Merchant, Arbitrator}, theo thứ tự bất kỳ.
Vì Trọng tài (sàn) luôn ký ngay lúc Admin tạo đề xuất, một chữ ký của Buyer HOẶC Merchant là đủ.
"""
from dataclasses import dataclass, fields

from .errors import DomainError

# Thứ tự trường PHẢI khớp shared/eip712/types.json#DisputeResolution (có test kiểm chéo) và DISPUTE_TYPEHASH trong contract.
DISPUTE_FIELDS = ('orderId', 'payoutTo', 'amount', 'nonce', 'deadline')

PARTY_BUYER = 'BUYER'
PARTY_MERCHANT = 'MERCHANT'
PARTY_ARBITRATOR = 'ARBITRATOR'
PARTIES = (PARTY_BUYER, PARTY_MERCHANT, PARTY_ARBITRATOR)

# Trạng thái dispute_resolutions mà việc nộp còn có nghĩa (SUBMITTED/EXECUTED = đã nộp; EXPIRED/CANCELLED = bỏ).
SUBMITTABLE = ('PROPOSED', 'READY')
DONE = ('SUBMITTED', 'EXECUTED')
DEAD = ('EXPIRED', 'CANCELLED')


@dataclass(frozen=True)
class DisputeResolution:
    orderId: int
    payoutTo: str
    amount: int
    nonce: int
    deadline: int

    def message(self):
        """Dạng JSON cho client: uint256 là chuỗi thập phân (SDD 8.2), địa chỉ giữ nguyên."""
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = str(v) if isinstance(v, int) else v
        return out


def pick_signature_pair(signatures):
    """`signatures`: [{'party', 'signature'}] ĐÃ xác minh. Trả (sig1, sig2) hoặc None nếu chưa đủ hai bên khác nhau.
    Ưu tiên Trọng tài + một bên (đủ ngay khi một bên đồng ý), nếu không có chữ ký Trọng tài thì Buyer + Merchant."""
    by_party = {}
    for s in signatures:
        by_party.setdefault(s['party'], s['signature'])      # mỗi bên một chữ ký (UNIQUE ở CSDL); lặp thì lấy cái đầu
    arb = by_party.get(PARTY_ARBITRATOR)
    for party in (PARTY_BUYER, PARTY_MERCHANT):
        if arb and party in by_party:
            return arb, by_party[party]
    if PARTY_BUYER in by_party and PARTY_MERCHANT in by_party:
        return by_party[PARTY_BUYER], by_party[PARTY_MERCHANT]
    return None


def parties_present(signatures):
    return sorted({s['party'] for s in signatures}, key=PARTIES.index)


def check_deadline(now, deadline, disputed_at, dispute_timeout):
    """Cùng hai điều kiện contract kiểm: chưa hết hạn, và hạn phải TRƯỚC khi Trọng tài có quyền xử đơn phương (R-02)."""
    if int(now) > int(deadline):
        raise DomainError('DISPUTE_EXPIRED', 'Đề xuất phán quyết đã hết hạn chữ ký, cần Admin tạo đề xuất mới.')
    if int(deadline) >= int(disputed_at) + int(dispute_timeout):
        raise DomainError('DISPUTE_STALE', 'Hạn chữ ký của đề xuất không hợp lệ so với thời hạn tranh chấp, cần đề xuất mới.')


def payout_side(payout_to, buyer, merchant):
    """'BUYER' (hoàn tiền) | 'MERCHANT' (giải ngân) | None nếu địa chỉ không thuộc đơn."""
    p = str(payout_to).lower()
    if p == str(buyer).lower():
        return PARTY_BUYER
    if p == str(merchant).lower():
        return PARTY_MERCHANT
    return None
