"""API Web3 (SRS 7, SDD 10): ví, tạo đơn + báo giá, lô thanh toán. Lỗi luôn dạng {code, message} tiếng Việt.

Danh tính chỉ lấy từ token (g.user_id), không nhận userId từ body/URL. Chỉ role user/seller dùng được ví và đặt hàng:
admin và shipper không phải bên mua/bán (shipper có khóa relayer riêng ở phía máy chủ).
"""
import logging

from flask import Blueprint, g, jsonify, request
from werkzeug.exceptions import HTTPException

from auth_utils import require_auth
from errors import ApiError
from routes.auth import get_db_connection
from validation import as_int, get_str, json_body

from ...domain.errors import DomainError, http_status
from ...ports.chain_port import ChainUnavailable
from . import container as c

log = logging.getLogger('slopee.web3')

shipper_bp = Blueprint('w3_shipper', __name__)
admin_w3_bp = Blueprint('w3_admin', __name__)
notifications_bp = Blueprint('w3_notifications', __name__)
disputes_bp = Blueprint('w3_disputes', __name__)
wallet_bp = Blueprint('w3_wallet', __name__)
orders_bp = Blueprint('w3_orders', __name__)
groups_bp = Blueprint('w3_groups', __name__)

BUYER_ROLES = ('user', 'seller')
MAX_CART_ITEMS = 100


def _err(code, message, status, extra=None):
    body = {'code': code, 'message': message}
    if extra:
        body.update(extra)
    resp = jsonify(body)
    resp.status_code = status
    return resp


def _on_domain_error(e):
    return _err(e.code, e.message, http_status(e.code), e.extra)


def _on_api_error(e):       # lỗi kiểm đầu vào của validation.py (P0-06) -> cùng dạng {code, message}
    return _err(e.code, e.message, e.status, e.extra)


def _on_chain_unavailable(e):
    log.warning('Chain unavailable: %s', e)
    return _err('CHAIN_UNAVAILABLE', 'Không kết nối được blockchain, hãy thử lại sau ít phút.', 503)


def _on_unexpected(e):
    if isinstance(e, HTTPException):
        return _err((e.name or 'error').lower().replace(' ', '_'), e.description or e.name, e.code or 500)
    log.error('Unhandled error in web3 API: %r', e, exc_info=True)      # chi tiết chỉ ở log (đã lọc dữ liệu nhạy cảm)
    return _err('internal_error', 'Đã có lỗi phía máy chủ, hãy thử lại sau.', 500)


for _bp in (wallet_bp, orders_bp, groups_bp, shipper_bp, admin_w3_bp, notifications_bp, disputes_bp):
    _bp.register_error_handler(DomainError, _on_domain_error)
    _bp.register_error_handler(ApiError, _on_api_error)
    _bp.register_error_handler(ChainUnavailable, _on_chain_unavailable)
    _bp.register_error_handler(Exception, _on_unexpected)


def _container():
    return c.get_container(lambda: get_db_connection())


# ------------------------------------------------------------------ UC-00
@wallet_bp.route('/nonce', methods=['POST'])
@require_auth(*BUYER_ROLES)
def wallet_nonce():
    data = json_body()
    # SDD 10.2 ghi "không có đầu vào", nhưng thông điệp SIWE phải chứa địa chỉ nên Frontend gửi địa chỉ MetaMask đang chọn.
    address = get_str(data, 'address', max_len=64, label='address')
    return jsonify(_container().wallet_service().issue_nonce(g.user_id, address)), 200


@wallet_bp.route('/link', methods=['POST'])
@require_auth(*BUYER_ROLES)
def wallet_link():
    data = json_body()
    address = get_str(data, 'address', max_len=64, label='address')
    signature = get_str(data, 'signature', max_len=200, label='signature')
    nonce = get_str(data, 'nonce', required=False, max_len=64, label='nonce')   # tùy chọn: bỏ qua thì dùng nonce mới nhất
    return jsonify(_container().wallet_service().link_wallet(g.user_id, address, signature, nonce)), 200


@wallet_bp.route('', methods=['GET'])
@require_auth(*BUYER_ROLES)
def wallet_get():
    return jsonify(_container().wallet_service().get_wallet(g.user_id)), 200


# ------------------------------------------------------------------ UC-01
def _cart_item_ids(data):
    raw = data.get('cart_item_ids')
    if not isinstance(raw, list) or not raw:
        raise DomainError('EMPTY_CART', 'Chưa chọn sản phẩm nào để thanh toán.')
    if len(raw) > MAX_CART_ITEMS:
        raise DomainError('INVALID_AMOUNT', f'Tối đa {MAX_CART_ITEMS} dòng sản phẩm mỗi lần thanh toán.')
    for v in raw:
        if not isinstance(v, str) or not v.strip() or len(v) > 36:
            raise DomainError('CART_ITEM_NOT_FOUND', 'Mã dòng giỏ hàng không hợp lệ.')
    return [v.strip() for v in raw]


@orders_bp.route('', methods=['POST'])
@require_auth(*BUYER_ROLES)
def create_order():
    ids = _cart_item_ids(json_body())
    return jsonify(_container().quote_service().create_checkout(g.user_id, ids)), 201


@orders_bp.route('/eligibility', methods=['POST'])
@require_auth(*BUYER_ROLES)
def web3_eligibility():
    """Chỉ đọc: các shop trong giỏ đã liên kết ví nhận tiền chưa (để Checkout ẩn/khóa lựa chọn Web3 thay vì để lỗi ở bước cuối)."""
    ids = _cart_item_ids(json_body())
    return jsonify(_container().quote_service().check_web3_eligibility(g.user_id, ids)), 200


@orders_bp.route('/<order_code>/status', methods=['GET'])
@require_auth(*BUYER_ROLES, 'admin')
def order_status(order_code):
    """Polling 2-3 giây (DD-04): trạng thái lấy từ MySQL do Indexer ghi, kèm server_time."""
    return jsonify(_container().order_status_service().get_status(g.user_id, g.role, order_code)), 200


@orders_bp.route('/<order_code>/dispute-note', methods=['POST'])
@require_auth(*BUYER_ROLES)
def dispute_note(order_code):
    """UC-05/SEQ-02: Buyer gửi lý do + đường dẫn bằng chứng SAU KHI Indexer đã ghi DISPUTED. Chỉ Buyer của đơn; gửi lại thì ghi đè.
    Giá trị thô được truyền thẳng cho service (kiểm kiểu và độ dài ở domain), danh tính chỉ từ token."""
    body = json_body()
    return jsonify(_container().dispute_note_service().save_note(
        g.user_id, order_code, body.get('reason'), body.get('evidence_url'))), 200


@groups_bp.route('/<group_id>/quote', methods=['POST'])
@require_auth(*BUYER_ROLES)
def requote_group(group_id):
    return jsonify(_container().quote_service().reissue_group_quotes(g.user_id, group_id)), 200


@groups_bp.route('/<group_id>', methods=['GET'])
@require_auth(*BUYER_ROLES)
def get_group(group_id):
    return jsonify(_container().quote_service().get_group(g.user_id, group_id)), 200


# ------------------------------------------------------------------ UC-03 (Tuần 5): cổng Shipper. CHỈ role `shipper`.
@shipper_bp.route('/orders', methods=['GET'])
@require_auth('shipper')
def shipper_orders():
    return jsonify(_container().shipper_service().list_orders(g.user_id)), 200


@shipper_bp.route('/orders/<order_code>/deliver', methods=['POST'])
@require_auth('shipper')
def shipper_deliver(order_code):
    """Relayer gửi confirmDelivery; trạng thái đơn do Indexer ghi sau đó (BR-09), nên trả outcome + tx_hash, không trả DELIVERED."""
    return jsonify(_container().shipper_service().deliver(g.user_id, order_code)), 200


# ------------------------------------------------------------------ Admin (Tuần 5). Mới ngoài danh sách SDD 10.2, chờ nhóm xác nhận
@admin_w3_bp.route('/reconcile', methods=['GET'])
@require_auth('admin')
def admin_reconcile():
    """AC-10: đối soát số dư contract với đơn đang mở. `?deep=1` so thêm trạng thái từng đơn với chuỗi (khi Indexer đã bắt kịp)."""
    deep = request.args.get('deep', '').lower() in ('1', 'true', 'yes')
    return jsonify(_container().reconcile_service().run(deep=deep)), 200


@admin_w3_bp.route('/orders/<order_code>/shipper', methods=['PUT'])
@require_auth('admin')
def admin_assign_shipper(order_code):
    """Gán/đổi Shipper cho đơn chưa giao (UC-03 cần dòng shipper_assignments). Người gán lấy từ token."""
    shipper = get_str(json_body(), 'shipper_user_id', max_len=36, label='shipper_user_id')
    return jsonify(_container().shipper_service().assign(g.user_id, order_code, shipper)), 200


@notifications_bp.route('', methods=['GET'])
@require_auth
def my_notifications():
    """Thông báo của chính người gọi (ví dụ: đơn đã giao kèm hạn khiếu nại). Danh tính chỉ từ token."""
    return jsonify(_container().notification_service().list_for_user(g.user_id)), 200


# ------------------------------------------------------------------ UC-06 (Tuần 6, A)
@disputes_bp.route('/<order_code>/submit', methods=['POST'])
@require_auth(*BUYER_ROLES, 'admin')
def dispute_submit(order_code):
    """Relayer nộp `resolveDispute` khi đủ chữ ký của hai bên khác nhau. Danh tính chỉ từ token; thân yêu cầu bị bỏ qua.
    Trạng thái đề xuất sang EXECUTED do Indexer (BR-09), nên trả outcome + tx_hash. B thêm GET/signatures vào cùng blueprint này."""
    return jsonify(_container().dispute_submit_service().submit(g.user_id, g.role, order_code)), 200


@admin_w3_bp.route('/disputes', methods=['GET'])
@require_auth('admin')
def admin_disputes():
    """Các đơn đang DISPUTED kèm ghi chú của Buyer, đề xuất mới nhất và các bên đã ký (màn hình Admin). Mới ngoài SDD 10.2."""
    return jsonify(_container().dispute_admin_service().list_open()), 200


# ------------------------------------------------------------------ UC-06 (Tuần 6, B): đề xuất + chữ ký + xem
@admin_w3_bp.route('/disputes/<order_code>/proposal', methods=['POST'])
@require_auth('admin')
def admin_dispute_proposal(order_code):
    """Admin chọn bên nhận tiền (`payout_to`: 'BUYER' | 'MERCHANT' | đúng địa chỉ ví của bên đó); Trọng tài ký ngay (UC-06 bước 1-2)."""
    body = json_body()
    return jsonify(_container().dispute_service().propose(g.user_id, order_code, body.get('payout_to'), body.get('reason_note'))), 201


@disputes_bp.route('/<order_code>', methods=['GET'])
@require_auth(*BUYER_ROLES, 'admin')
def get_dispute(order_code):
    """Đề xuất + danh sách chữ ký (không có chữ ký thô) + ghi chú khiếu nại. Chỉ Buyer/Merchant của đơn hoặc Admin."""
    return jsonify(_container().dispute_service().get(g.user_id, g.role, order_code)), 200


@disputes_bp.route('/<order_code>/signatures', methods=['POST'])
@require_auth(*BUYER_ROLES)
def add_dispute_signature(order_code):
    """Bên (Buyer/Merchant) được xác định từ token, không do client chọn (SDD 10.2). Admin không ký thay."""
    body = json_body()
    rid = as_int(body.get('resolution_id'), 'resolution_id', minimum=1)
    return jsonify(_container().dispute_service().add_signature(g.user_id, order_code, rid, body.get('signature'))), 200

