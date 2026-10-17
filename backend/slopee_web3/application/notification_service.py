"""Thông báo cho người dùng (NotificationPort, SDD 5.2). Ghi do Indexer (ORDER_DELIVERED) và tác vụ nền (DELIVERY_TIMEOUT)."""

LIST_LIMIT = 50


class NotificationService:
    def __init__(self, uow_factory):
        self._uow = uow_factory

    def list_for_user(self, user_id):
        with self._uow() as uow:
            return {'notifications': uow.notifications.list_for_user(user_id, LIST_LIMIT)}
