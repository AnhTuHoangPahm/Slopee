// Đồng hồ máy chủ cho các hạn "tuyệt đối" (hạn chữ ký phán quyết, ...). Hàm thuần, dễ test.
// `server_time` từ API luôn CŨ hơn giờ thật của chuỗi 0-2 giây (block 2 giây) cộng độ trễ mạng, KHÔNG BAO GIỜ mới hơn. Vì vậy
// mẫu `server_time - now_client` luôn là CẬN DƯỚI của độ lệch thật và mẫu LỚN NHẤT là ước lượng tốt nhất: chỉ tăng, nên
// đồng hồ đếm ngược không bao giờ giật lùi khi một lần poll bị trễ (đo được ~1,5 giây răng cưa trên Anvil đã tua giờ).

/** Độ lệch mới (giây) sau khi nhận một mẫu. `prev` null = chưa có. Lệch ngược quá `resetAfterSec` thì neo lại (đồng hồ chuỗi bị đặt lại). */
export function nextOffset(prev, serverTimeSec, nowMs, resetAfterSec = 30) {
    const observed = Number(serverTimeSec) - nowMs / 1000;
    if (!Number.isFinite(observed)) return prev ?? null;
    if (prev === null || prev === undefined || observed > prev) return observed;
    if (prev - observed > resetAfterSec) return observed;
    return prev;
}

/** Số giây còn lại tới `deadlineSec` (mốc UTC) theo giờ máy chủ ước lượng; null nếu chưa có độ lệch. */
export function remainingSec(deadlineSec, offset, nowMs) {
    if (offset === null || offset === undefined || deadlineSec === null || deadlineSec === undefined) return null;
    return Number(deadlineSec) - (nowMs / 1000 + offset);
}

/** Giờ máy chủ ước lượng (giây UTC, có phần thập phân) tại `nowMs` của máy khách; null nếu chưa có độ lệch. */
export function serverNowSec(offset, nowMs) {
    if (offset === null || offset === undefined) return null;
    return nowMs / 1000 + offset;
}

/**
 * Đồng hồ máy chủ có trạng thái cho MỘT nguồn polling: mỗi lần nhận phản hồi gọi `observe(server_time)` NGAY TRONG hàm poll (cùng nhịp với dữ liệu,
 * không đợi một useEffect, để không có lần render nào có dữ liệu mà chưa có đồng hồ). Chỉ giữ độ lệch lớn nhất (xem nextOffset) nên không giật lùi.
 * Không phải hook: đặt trong useRef, hoặc dùng thẳng khi test.
 */
export function createServerClock({ resetAfterSec = 30, now = Date.now } = {}) {
    let offset = null;
    return {
        /** Nhận một mẫu; trả độ lệch hiện hành. `nowMs` là lúc NHẬN phản hồi (mặc định: bây giờ). */
        observe(serverTimeSec, nowMs = now()) {
            offset = nextOffset(offset, serverTimeSec, nowMs, resetAfterSec);
            return offset;
        },
        get offset() { return offset; },
        nowSec(nowMs = now()) { return serverNowSec(offset, nowMs); },
        remaining(deadlineSec, nowMs = now()) { return remainingSec(deadlineSec, offset, nowMs); },
        reset() { offset = null; },
    };
}

