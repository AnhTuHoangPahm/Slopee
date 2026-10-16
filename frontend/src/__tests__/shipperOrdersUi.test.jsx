import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ShipperOrders from '../pages/ShipperOrders';
import RequireRole from '../components/RequireRole';
import { Web3ApiError } from '../lib/errors';
import * as shipperApi from '../api/shipper';

configure({ asyncUtilTimeout: 4000 });
vi.mock('../api/shipper');

const ORDER = { order_id: 'ord-12345678-aaaa', status: 'LOCKED', shop_name: 'Shop A', buyer_name: 'An', price_vnd: 250000 };
const mount = () => render(<MemoryRouter initialEntries={['/shipper/orders']}><Routes>
    <Route path="/shipper/orders" element={<RequireRole roles="shipper"><ShipperOrders /></RequireRole>} />
</Routes></MemoryRouter>);

beforeEach(() => {
    sessionStorage.setItem('token', 't');
    sessionStorage.setItem('user', JSON.stringify({ id: 's1', name: 'Giao', role: 'shipper' }));
});
afterEach(() => { sessionStorage.clear(); vi.resetAllMocks(); });

describe('ShipperOrders (UC-03)', () => {
    it('liệt kê đơn LOCKED kèm giá VND và nút xác nhận', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([ORDER]);
        mount();
        const row = await screen.findByTestId(`order-${ORDER.order_id}`);
        expect(row.textContent).toMatch(/Shop A/);
        expect(row.textContent).toMatch(/250\.000/);
        expect(screen.getByRole('button', { name: 'Xác nhận phát hàng thành công' })).toBeTruthy();
    });

    it('danh sách rỗng -> thông báo chưa có đơn', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([]);
        mount();
        expect(await screen.findByTestId('shipper-empty')).toBeTruthy();
    });

    it('phải bấm xác nhận HAI bước; "Chưa" quay lại mà không gọi API', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([ORDER]);
        mount();
        fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận phát hàng thành công' }));
        fireEvent.click(screen.getByRole('button', { name: 'Chưa' }));
        expect(shipperApi.deliverShipperOrderAPI).not.toHaveBeenCalled();
        expect(screen.getByRole('button', { name: 'Xác nhận phát hàng thành công' })).toBeTruthy();
    });

    it('đường vui: gọi API đúng mã đơn, hiện đã gửi + mã giao dịch, khóa nút chờ Indexer', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([ORDER]);
        shipperApi.deliverShipperOrderAPI.mockResolvedValue({ outcome: 'SENT', tx_hash: `0x${'ab'.repeat(32)}` });
        mount();
        fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận phát hàng thành công' }));
        fireEvent.click(screen.getByRole('button', { name: 'Đúng, xác nhận' }));
        const ok = await screen.findByTestId(`sent-${ORDER.order_id}`);
        expect(shipperApi.deliverShipperOrderAPI).toHaveBeenCalledWith(ORDER.order_id);
        expect(ok.textContent).toMatch(/blockchain/);
        expect(ok.textContent).toMatch(/0xababab…abab/);
        const btn = screen.getByRole('button', { name: 'Đang chờ hệ thống ghi nhận…' });
        expect(btn.disabled).toBe(true);
    });

    it('bấm đúp nhanh chỉ gửi MỘT yêu cầu', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([ORDER]);
        let release;
        shipperApi.deliverShipperOrderAPI.mockImplementation(() => new Promise((r) => { release = () => r({ outcome: 'SENT', tx_hash: null }); }));
        mount();
        fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận phát hàng thành công' }));
        const yes = screen.getByRole('button', { name: 'Đúng, xác nhận' });
        fireEvent.click(yes);
        fireEvent.click(yes);
        await waitFor(() => expect(shipperApi.deliverShipperOrderAPI).toHaveBeenCalledTimes(1));
        release();
        await screen.findByTestId(`sent-${ORDER.order_id}`);
        expect(shipperApi.deliverShipperOrderAPI).toHaveBeenCalledTimes(1);
    });

    it('lỗi API (INVALID_STATE) hiện thông báo tiếng Việt và cho thử lại', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([ORDER]);
        shipperApi.deliverShipperOrderAPI.mockRejectedValue(new Web3ApiError({ code: 'INVALID_STATE', status: 409 }));
        mount();
        fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận phát hàng thành công' }));
        fireEvent.click(screen.getByRole('button', { name: 'Đúng, xác nhận' }));
        const alert = await screen.findByRole('alert');
        expect(alert.textContent).toMatch(/không còn ở trạng thái/);
        expect(screen.getByRole('button', { name: 'Xác nhận phát hàng thành công' }).disabled).toBe(false);
    });

    it('lỗi tải danh sách hiện cảnh báo nhưng không làm sập trang', async () => {
        shipperApi.fetchShipperOrdersAPI.mockRejectedValue(new Web3ApiError({ code: 'CHAIN_UNAVAILABLE', status: 503 }));
        mount();
        expect((await screen.findByRole('alert')).textContent).toMatch(/blockchain/);
    });

    it('đơn DELIVERED chỉ xem, không có nút xác nhận', async () => {
        shipperApi.fetchShipperOrdersAPI.mockResolvedValue([{ ...ORDER, status: 'DELIVERED', delivered_at: 1800000100 }]);
        mount();
        await screen.findByText(/Đã giao, chờ người mua kiểm tra/);
        expect(screen.queryByRole('button', { name: 'Xác nhận phát hàng thành công' })).toBeNull();
    });

    it('route chỉ cho role shipper: user thường thấy thông báo không đủ quyền và API không bị gọi', async () => {
        sessionStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'An', role: 'user' }));
        mount();
        expect(await screen.findByText('Bạn không có quyền truy cập trang này')).toBeTruthy();
        expect(shipperApi.fetchShipperOrdersAPI).not.toHaveBeenCalled();
    });
});
