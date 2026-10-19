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


# ------------------------------------------------------------------ Tuần 6 (B): tạo đề xuất và nhận chữ ký
DEFAULT_SIG_TTL_SECONDS = 604800                         # 7 ngày (platform_settings.DISPUTE_SIG_TTL_SECONDS)
ACTIVE_STATES = SUBMITTABLE + ('SUBMITTED',)             # mỗi đơn chỉ có MỘT đề xuất đang hoạt động


def compute_deadline(now_chain, ttl, disputed_at, dispute_timeout):
    """`min(now_chain + TTL, disputedAt + disputeTimeout - 1)`: chữ ký luôn hết hạn TRƯỚC khi Trọng tài có quyền xử đơn phương
    (contract cũng từ chối `deadline >= disputedAt + disputeTimeout`, nên hai đường xử lý không bao giờ cùng hợp lệ, R-02)."""
    return min(int(now_chain) + int(ttl), int(disputed_at) + int(dispute_timeout) - 1)


def parse_payout(value, buyer, merchant):
    """`value` là 'buyer'/'merchant' (không phân biệt hoa thường; giao diện của A gửi 'BUYER'/'MERCHANT') hoặc đúng địa chỉ Buyer/Merchant
    của đơn trên chuỗi. Trả (bên_được_nhận, địa_chỉ). Giá trị khác (kể cả địa chỉ lạ) bị từ chối: contract cũng revert 'Invalid payout recipient'."""
    if not isinstance(value, str) or not value.strip():
        raise DomainError('INVALID_PAYOUT', 'Hãy chọn bên được nhận tiền: người mua (hoàn tiền) hoặc người bán (giải ngân).')
    v = value.strip().lower()
    if v == 'buyer' or v == str(buyer).lower():
        return PARTY_BUYER, buyer
    if v == 'merchant' or v == str(merchant).lower():
        return PARTY_MERCHANT, merchant
    raise DomainError('INVALID_PAYOUT', 'Bên được nhận tiền phải là người mua hoặc người bán của đơn này.')


def party_of(user_id, buyer_user_id, merchant_user_id):
    """Bên của người dùng trong đơn, suy từ TOKEN (không do client chọn). None nếu không phải Buyer/Merchant."""
    if user_id == buyer_user_id:
        return PARTY_BUYER
    if user_id == merchant_user_id:
        return PARTY_MERCHANT
    return None


def is_ready(signed_parties):
    """Đủ 2/3: Trọng tài + một bên, hoặc cả Buyer và Merchant (hai bên KHÁC NHAU, đúng điều contract cần)."""
    signed = set(signed_parties)
    if PARTY_ARBITRATOR in signed and signed & {PARTY_BUYER, PARTY_MERCHANT}:
        return True
    return {PARTY_BUYER, PARTY_MERCHANT} <= signed


def clean_note(value, limit=2000):
    """Ghi chú thẩm định của Admin: tùy chọn, tối đa `limit` ký tự."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError('INVALID_DISPUTE_NOTE', 'Ghi chú thẩm định phải là chuỗi ký tự.')
    note = value.strip()
    if len(note) > limit:
        raise DomainError('INVALID_DISPUTE_NOTE', f'Ghi chú thẩm định tối đa {limit} ký tự.')
    return note or None

