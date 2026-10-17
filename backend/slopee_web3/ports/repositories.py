"""Repositories + UnitOfWork (SDD 5.2). Mỗi nhóm bảng một repository; giao dịch qua UnitOfWork.

Hợp đồng chung: mọi hàm nhận/trả kiểu Python thuần (dict, int, str). Số tiền token luôn là `int` ở đây
và chỉ thành chuỗi ở biên lưu trữ/JSON (SDD 7.5: không bao giờ float).
"""
from typing import Optional, Protocol


class DuplicateWallet(Exception):
    """Vi phạm UNIQUE(address) khi chèn ví (hai tài khoản tranh nhau cùng một ví)."""


class WalletRepo(Protocol):
    def active_wallet(self, user_id: str) -> Optional[dict]: ...            # {'address', 'linked_at'}
    def active_wallets(self, user_ids: list) -> dict: ...                    # {user_id: address}
    def count_recent_nonces(self, user_id: str, within_seconds: int, ttl: int) -> int: ...
    def insert_nonce(self, nonce: str, user_id: str, ttl: int) -> int: ...   # trả expires_at (giây UTC, giờ DB)
    def find_nonce(self, user_id: str, nonce: Optional[str]) -> Optional[dict]: ...  # {'nonce','expires_at'} còn dùng được
    def consume_nonce(self, nonce: str, user_id: str) -> bool: ...           # nguyên tử (SDD 5.3g)
    def wallet_by_address(self, address: str) -> Optional[dict]: ...         # {'id','user_id','is_active','linked_at'}, đọc không khóa
    def deactivate_user_wallets(self, user_id: str) -> None: ...
    def activate_wallet(self, wallet_id: int) -> None: ...
    def insert_wallet(self, user_id: str, address: str) -> int: ...          # trả linked_at; ném DuplicateWallet


class SettingsRepo(Protocol):
    def get_many(self, keys: list) -> dict: ...                              # {key: value-string}; thiếu khóa thì vắng mặt


class PolicyRepo(Protocol):
    def policies_for_categories(self, category_ids: list) -> Optional[dict]: ...  # {category_id: Policy}; None nếu thiếu nhóm mặc định


class CheckoutRepo(Protocol):
    def lock_cart_lines(self, user_id: str, cart_item_ids: list, lock: bool = True) -> list: ...
    def lock_products(self, product_ids: list, lock: bool = True) -> dict: ...
    def get_shops(self, shop_ids: list) -> dict: ...
    def pending_group_for_products(self, user_id: str, product_ids: list) -> Optional[str]: ...
    def next_onchain_id(self) -> int: ...
    def insert_group(self, group_id, buyer_user_id, token_address, total_amount_raw, order_count) -> None: ...
    def insert_order(self, order_id, user_id, total_vnd, created_at) -> None: ...
    def insert_order_lines(self, order_id, lines: list) -> None: ...
    def reserve_stock(self, product_id, quantity) -> bool: ...
    def release_stock(self, product_id, quantity) -> None: ...
    def insert_order_web3(self, row: dict) -> None: ...
    def insert_quote(self, order_id, quote_json: dict, signature: str, deadline: int) -> None: ...
    def get_group(self, group_id: str, buyer_user_id: str) -> Optional[dict]: ...
    def group_orders(self, group_id: str, lock: bool = False) -> list: ...
    def order_lines(self, order_id: str) -> list: ...
    def update_order_requote(self, order_id: str, fields: dict) -> None: ...
    def update_group_total(self, group_id: str, total_amount_raw: str) -> None: ...
    def latest_quote(self, order_id: str) -> Optional[dict]: ...
    def order_status_row(self, order_id: str) -> Optional[dict]: ...        # đọc không khóa; None nếu không phải đơn Web3


class ShipperRepo(Protocol):
    def get_user(self, user_id: str) -> Optional[dict]: ...                        # {'id','role','name'}
    def assigned_orders(self, shipper_user_id: str, statuses: tuple) -> list: ...  # đơn gán cho Shipper theo trạng thái Web3
    def assigned_order(self, order_id: str, shipper_user_id: str, lock: bool = False) -> Optional[dict]: ...
    def order_for_assignment(self, order_id: str, lock: bool = False) -> Optional[dict]: ...  # {'order_id','status'}
    def assign(self, order_id: str, shipper_user_id: str, assigned_by: Optional[str]) -> None: ...


class OutboxRepo(Protocol):
    """Nhật ký giao dịch relayer (bảng tx_outbox): PENDING -> SENT -> CONFIRMED | FAILED. Chỉ để truy vết/gỡ lỗi."""
    def insert(self, kind: str, order_id: str) -> int: ...                  # trả id, status = PENDING
    def mark_sent(self, outbox_id: int, tx_hash: str) -> None: ...
    def mark_confirmed(self, outbox_id: int) -> None: ...
    def mark_failed(self, outbox_id: int, error: str) -> None: ...
    def recent_for_order(self, order_id: str, limit: int = 20) -> list: ...  # mới nhất trước


class NotificationRepo(Protocol):
    def add(self, user_id: str, order_id: str, kind: str, message: str) -> bool: ...  # False nếu đã gửi (UNIQUE) ⇒ idempotent
    def list_for_user(self, user_id: str, limit: int) -> list: ...


class JobsRepo(Protocol):
    def expired_quote_candidates(self, now: int, grace: int, limit: int) -> list: ...   # group_id có đơn PENDING_PAYMENT quá hạn
    def lock_group_orders(self, group_id: str) -> list: ...                             # đơn của lô, FOR UPDATE, kèm hạn báo giá mới nhất
    def expire_order(self, order_id: str) -> bool: ...                                  # PENDING_PAYMENT -> EXPIRED (+ orders cũ); False nếu đã đổi
    def delivered_due(self, now: int, limit: int) -> list: ...                          # đơn DELIVERED đã hết hạn kiểm tra
    def locked_past_delivery_timeout(self, now: int, limit: int) -> list: ...           # đơn LOCKED quá 14 ngày


class ReconcileRepo(Protocol):
    def indexer_cursor(self) -> Optional[dict]: ...                                     # {'last_block','last_block_hash'}
    def open_totals(self) -> list: ...                                                  # [{'token','orders','amount_raw'(int)}]
    def pending_totals(self) -> list: ...                                               # [{'token','amount_raw'(int)}]
    def anomaly_orders(self) -> list: ...                                               # đơn anomaly_flag = 1
    def open_orders(self, limit: int) -> list: ...                                      # [{'order_id','onchain_order_id','status'}]


class DisputeNoteRepo(Protocol):
    def order_for_note(self, order_id: str, lock: bool = False) -> Optional[dict]: ...   # {'order_id','buyer_user_id','status'}
    def has_resolution(self, order_id: str) -> bool: ...                                 # Admin đã có đề xuất phán quyết
    def upsert(self, order_id: str, buyer_user_id: str, reason: str, evidence_url: Optional[str]) -> bool: ...  # True nếu tạo mới
    def get(self, order_id: str) -> Optional[dict]: ...


class UnitOfWork(Protocol):
    wallets: WalletRepo
    settings: SettingsRepo
    policies: PolicyRepo
    checkout: CheckoutRepo
    shipper: ShipperRepo
    outbox: OutboxRepo
    notifications: NotificationRepo
    jobs: JobsRepo
    reconcile: ReconcileRepo
    dispute_notes: DisputeNoteRepo

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...   # chưa commit thì ROLLBACK
    def commit(self) -> None: ...
