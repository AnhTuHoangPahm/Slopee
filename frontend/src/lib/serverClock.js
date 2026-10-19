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
