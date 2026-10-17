// Nhãn và màu hiển thị cho trạng thái đơn Web3 (SRS 5, 5.1). Trạng thái thật do Indexer ghi (BR-09); đây chỉ là cách hiển thị.
export const STATUS_LABEL = Object.freeze({
    PENDING_PAYMENT: 'Chờ thanh toán',
    EXPIRED: 'Hết hạn thanh toán',
    LOCKED: 'Đã ký quỹ, chờ giao hàng',
    DELIVERED: 'Đã giao, đang kiểm tra hàng',
    DISPUTED: 'Khiếu nại Web3',
    COMPLETED: 'Hoàn tất',
    REFUNDED: 'Đã hoàn tiền',
});

// DISPUTED dùng huy hiệu vàng (SRS 5.1); trạng thái hủy/hoàn tiền màu đỏ; còn lại xanh như giao diện cũ.
export const STATUS_COLOR = Object.freeze({
    PENDING_PAYMENT: '#888', EXPIRED: '#d32f2f', LOCKED: '#1976d2', DELIVERED: '#26aa99',
    DISPUTED: '#b8860b', COMPLETED: '#2e7d32', REFUNDED: '#d32f2f',
});

export const statusLabel = (s) => STATUS_LABEL[s] ?? String(s ?? '');
