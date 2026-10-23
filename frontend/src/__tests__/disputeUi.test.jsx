import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Dispute from '../pages/Dispute';
import { WalletProvider } from '../hooks/useWallet';
import { parseDeployment } from '../lib/chain';
import { SIGN_WARNING_TEXT } from '../lib/disputeSign';
import { installDisputeMock } from '../mocks/disputeMock';
import { ADDR, ESCROW, WALLET } from './helpers/disputeFixtures';

// Tuần 6 [F] (UC-06, SDD 9.7): màn hình ký phán quyết. Ví giả ký bằng KHÓA THẬT (eth_signTypedData_v4) và mock API KIỂM CHỮ KÝ bằng
// mật mã thật (khôi phục địa chỉ, so với ví đã liên kết) nên nếu trang ký sai dữ liệu/sai ví thì test đỏ, không cần chuỗi thật.
configure({ asyncUtilTimeout: 6000 });
vi.setConfig({ testTimeout: 20000 });

const deployment = parseDeployment({ chainId: 31337, escrow: ESCROW, mockUSD: '0x5FbDB2315678afecb367f032d93F642f64180aa3', deployBlock: 1, token: { symbol: 'MUSD', decimals: 6 } });

/** EIP-1193 giả: chưa kết nối thì eth_accounts rỗng; ký typed data bằng ví thật; đếm số lần hiện hộp ký. */
function fakeProvider(wallet, { chainId = '0x7a69', rejectSign = false } = {}) {
    let connected = false;
    const request = vi.fn(async ({ method, params }) => {
        switch (method) {
            case 'eth_requestAccounts': connected = true; return [wallet.address];
            case 'eth_accounts': return connected ? [wallet.address] : [];
            case 'eth_chainId': return chainId;
            case 'net_version': return String(parseInt(chainId, 16));
            case 'eth_signTypedData_v4': {
                if (rejectSign) throw Object.assign(new Error('User rejected the request.'), { code: 4001 });
                const data = JSON.parse(params[1]);
                const { EIP712Domain: _omit, ...types } = data.types;
                return wallet.signTypedData(data.domain, types, data.message);
            }
            default: throw Object.assign(new Error(`unhandled ${method}`), { code: -32601 });
        }
    });
    return { request, on: vi.fn(), removeListener: vi.fn() };
}
const signCalls = (p) => p.request.mock.calls.filter(([a]) => a.method === 'eth_signTypedData_v4').length;

let mock;
beforeEach(() => {
    sessionStorage.setItem('token', 't');
    sessionStorage.setItem('user', JSON.stringify({ id: 'u1', name: 'An', role: 'user' }));
    mock = installDisputeMock({ latencyMs: 0, autoExecuteMs: null, buyerWallet: ADDR.buyer, merchantWallet: ADDR.merchant });
});
afterEach(() => { mock.uninstall(); sessionStorage.clear(); vi.restoreAllMocks(); });

function show({ wallet = WALLET.buyer, provider = fakeProvider(wallet), pageProps = {} } = {}) {
    render(
        <MemoryRouter initialEntries={['/disputes/mock-dispute-1']}>
            <WalletProvider provider={provider} deployment={deployment}>
                <Routes>
                    <Route path="/disputes/:code" element={<Dispute hideNavbar pollMs={40} {...pageProps} />} />
                    <Route path="/orders" element={<div>orders</div>} />
                </Routes>
            </WalletProvider>
        </MemoryRouter>,
    );
    return provider;
}
const connect = async () => fireEvent.click(await screen.findByTestId('gate-connect'));

describe('Dispute — Buyer nhận hoàn tiền (đường vui, ký thật)', () => {
    it('xem khiếu nại + đề xuất -> kết nối ví -> đọc cảnh báo -> ký -> READY -> thi hành -> EXECUTED', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        const provider = show();

        // khiếu nại, kết quả, số tiền và địa chỉ nhận hiển thị trước khi ký
        expect((await screen.findByTestId('complaint-reason')).textContent).toMatch(/bị vỡ góc/);
        expect(screen.getByTestId('outcome').dataset.outcome).toBe('REFUND_BUYER');
        expect(screen.getByTestId('outcome').textContent).toBe('Hoàn tiền cho Buyer');
        expect(screen.getByTestId('outcome-amount').textContent).toBe('25,00 mUSD');
        expect(screen.getByTestId('outcome-recipient').textContent).toBe(ADDR.buyer);
        expect(screen.getByTestId('signatures').querySelector('[data-party="ARBITRATOR"]').dataset.signed).toBe('true');
        expect(screen.getByTestId('signatures').querySelector('[data-party="BUYER"]').dataset.signed).toBe('false');

        // chưa kết nối/chưa đồng ý: không ký được
        expect(screen.getByTestId('sign-btn').disabled).toBe(true);
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        expect(screen.getByTestId('sign-btn').disabled).toBe(true); // còn thiếu ô đồng ý
        fireEvent.click(screen.getByTestId('ack'));
        await waitFor(() => expect(screen.getByTestId('sign-btn').disabled).toBe(false));

        fireEvent.click(screen.getByTestId('sign-btn'));
        await waitFor(() => expect(screen.getByTestId('phase-ready')).toBeTruthy());
        expect(signCalls(provider)).toBe(1);
        const post = mock.state.calls.find((c) => c.method === 'POST' && c.path.endsWith('/signatures'));
        expect(post.body).toMatchObject({ resolution_id: 1 });
        expect(post.body.signature).toMatch(/^0x[0-9a-f]{130}$/); // mock đã khôi phục đúng địa chỉ Buyer từ chữ ký này
        expect(mock.state.resolution.signatures.map((s) => s.party)).toEqual(['ARBITRATOR', 'BUYER']);
        expect(screen.getByTestId('signatures').querySelector('[data-party="BUYER"]').dataset.signed).toBe('true');
        expect(screen.queryByTestId('sign-btn')).toBeNull(); // đã ký thì không ký lại

        fireEvent.click(screen.getByTestId('execute-btn'));
        await waitFor(() => expect(screen.getByTestId('phase-submitted').textContent).toMatch(/Đang chờ hệ thống xác nhận/));
        expect(mock.state.resolution.status).toBe('SUBMITTED');

        mock.state.execute(); // Indexer ghi OrderRefunded
        await waitFor(() => expect(screen.getByTestId('phase-executed').textContent).toMatch(/Đã hoàn tiền cho Buyer/));
        const calls = mock.state.calls.length;
        await new Promise((r) => setTimeout(r, 160));
        expect(mock.state.calls.length).toBe(calls); // đã thi hành: polling dừng hẳn
    });

    it('cảnh báo màu vàng NGAY TRƯỚC nút ký, đúng nguyên văn SDD 9.7', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        show();
        const warning = await screen.findByTestId('sign-warning');
        expect(warning.textContent).toContain(SIGN_WARNING_TEXT);
        expect(warning.style.background).toMatch(/255, 243, 205|#fff3cd/i);
        const section = screen.getByTestId('sign-section');
        expect(section.firstElementChild).toBe(warning); // cảnh báo là phần tử đầu, trước ô đồng ý và nút ký
        expect(warning.compareDocumentPosition(screen.getByTestId('sign-btn')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
});

describe('Dispute — Merchant nhận giải ngân', () => {
    it('hiển thị phần thực nhận sau phí và ký bằng ví Merchant', async () => {
        mock.state.forceRole = 'MERCHANT';
        mock.state.propose({ payoutTo: 'merchant' });
        const provider = show({ wallet: WALLET.merchant });
        await screen.findByTestId('outcome');
        expect(screen.getByTestId('outcome').textContent).toBe('Giải ngân cho Merchant');
        expect(screen.getByTestId('outcome-amount').textContent).toBe('24,25 mUSD'); // 25 trừ phí 3%
        expect(screen.getByTestId('proposal').textContent).toMatch(/Đã trừ phí sàn 0,75 mUSD/);
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        fireEvent.click(screen.getByTestId('ack'));
        fireEvent.click(screen.getByTestId('sign-btn'));
        await waitFor(() => expect(screen.getByTestId('phase-ready')).toBeTruthy());
        expect(signCalls(provider)).toBe(1);
        expect(mock.state.resolution.signatures.map((s) => s.party)).toEqual(['ARBITRATOR', 'MERCHANT']);
    });
});

describe('Dispute — an toàn: không ký khi sai ví hay đề xuất bất thường', () => {
    it('ví khác ví đã liên kết: cảnh báo, không bật nút ký, không bật hộp ký', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        const provider = show({ wallet: WALLET.stranger });
        await connect();
        expect(await screen.findByTestId('gate-wrong-account')).toBeTruthy();
        fireEvent.click(screen.getByTestId('ack'));
        expect(screen.getByTestId('sign-btn').disabled).toBe(true);
        expect(signCalls(provider)).toBe(0);
    });

    it('sai mạng: có nút chuyển mạng, nút ký khóa', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        show({ provider: fakeProvider(WALLET.buyer, { chainId: '0x1' }) });
        await connect();
        expect(await screen.findByTestId('gate-switch')).toBeTruthy();
        expect(screen.getByTestId('sign-btn').disabled).toBe(true);
    });

    it('địa chỉ nhận không phải Buyer/Merchant: chặn hẳn, không có nút ký, nêu lý do', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: ADDR.stranger });
        show();
        const blocked = await screen.findByTestId('phase-blocked');
        expect(blocked.textContent).toMatch(/không phải ví của Buyer hay Merchant/);
        expect(screen.queryByTestId('sign-btn')).toBeNull();
        expect(screen.getByTestId('outcome').dataset.outcome).toBe('UNKNOWN');
    });

    it('số tiền đề xuất khác số ký quỹ: chặn', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        mock.state.resolution.amount_raw = '24000000';
        show();
        expect((await screen.findByTestId('phase-blocked')).textContent).toMatch(/không khớp số tiền ký quỹ/);
        expect(screen.queryByTestId('sign-btn')).toBeNull();
    });

    it('đề xuất đã hết hạn: không cho ký, báo chờ đề xuất mới và nhắc mốc Trọng tài đơn phương', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        mock.state.expire();
        show();
        const expired = await screen.findByTestId('phase-expired');
        expect(expired.textContent).toMatch(/Đề xuất đã hết hạn/);
        expect(expired.textContent).toMatch(/Trọng tài được xử đơn phương/);
        expect(screen.queryByTestId('sign-btn')).toBeNull();
    });

    it('hạn ký hết thì tự chuyển sang trạng thái hết hạn và gỡ nút ký', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer', ttlSec: 2 });
        show();
        await screen.findByTestId('sign-btn');
        await waitFor(() => expect(screen.getByTestId('phase-expired')).toBeTruthy(), { timeout: 6000 });
        expect(screen.queryByTestId('sign-btn')).toBeNull();
    });

    it('đếm hạn ký theo giờ MÁY CHỦ khi đồng hồ máy khách lệch 3 ngày (không dùng giờ máy khách)', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.serverSkewSec = -3 * 86400; // máy chủ chậm 3 ngày so với máy khách
        mock.state.propose({ payoutTo: 'buyer', ttlSec: 7 * 86400 });
        show();
        const el = await screen.findByTestId('deadline');
        // theo giờ máy chủ còn ~7 ngày; nếu tính nhầm theo giờ máy khách sẽ ra ~4 ngày
        await waitFor(() => expect(el.textContent).toMatch(/Hạn ký còn (7 ngày|6 ngày 23:59)/));
        expect(el.textContent).not.toMatch(/4 ngày|3 ngày/);
    });
});

describe('Dispute — chưa có đề xuất / hiển thị an toàn dữ liệu của người khác', () => {
    it('chưa có đề xuất: báo đang thẩm định, đề xuất xuất hiện khi Admin tạo (polling)', async () => {
        mock.state.forceRole = 'BUYER';
        show();
        expect(await screen.findByTestId('phase-awaiting')).toBeTruthy();
        expect(screen.queryByTestId('sign-btn')).toBeNull();
        mock.state.propose({ payoutTo: 'buyer' });
        await waitFor(() => expect(screen.getByTestId('sign-section')).toBeTruthy());
    });

    it('lý do khiếu nại chứa HTML được hiển thị như CHỮ, không chạy', async () => {
        mock.state.forceRole = 'MERCHANT';
        mock.state.note.reason = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
        show({ wallet: WALLET.merchant });
        const el = await screen.findByTestId('complaint-reason');
        expect(el.textContent).toBe('<img src=x onerror="alert(1)"><script>alert(2)</script>');
        expect(el.querySelector('img,script')).toBeNull();
    });

    it('liên kết bằng chứng: https mở an toàn, javascript:/data: KHÔNG thành liên kết', async () => {
        mock.state.forceRole = 'MERCHANT';
        show({ wallet: WALLET.merchant });
        const link = await within(await screen.findByTestId('complaint')).findByRole('link');
        expect(link.getAttribute('href')).toBe('https://example.com/evidence/photo-1.jpg');
        expect(link.getAttribute('rel')).toMatch(/noopener/);
        expect(link.getAttribute('rel')).toMatch(/noreferrer/);
        expect(link.getAttribute('target')).toBe('_blank');
    });

    it.each(['javascript:alert(1)', 'data:text/html,<script>1</script>', 'file:///etc/passwd'])('đường dẫn nguy hiểm %s không thành liên kết', async (url) => {
        mock.state.forceRole = 'MERCHANT';
        mock.state.note.evidence_url = url;
        show({ wallet: WALLET.merchant });
        const box = await screen.findByTestId('complaint');
        expect(within(box).queryByRole('link')).toBeNull();
        expect(box.textContent).toMatch(/không an toàn/);
    });

    it('đơn không tồn tại/không có quyền: báo lỗi rõ', async () => {
        render(
            <MemoryRouter initialEntries={['/disputes/khong-co']}><WalletProvider provider={fakeProvider(WALLET.buyer)} deployment={deployment}>
                <Routes><Route path="/disputes/:code" element={<Dispute hideNavbar pollMs={40} />} /></Routes>
            </WalletProvider></MemoryRouter>,
        );
        expect((await screen.findByRole('alert')).textContent).toMatch(/Không tìm thấy đơn hàng/);
    });
});

describe('Dispute — lỗi khi ký/gửi', () => {
    it('hủy trong MetaMask: thông báo nhẹ, nút ký dùng lại được, không gửi gì cho sàn', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        const provider = show({ provider: fakeProvider(WALLET.buyer, { rejectSign: true }) });
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        fireEvent.click(screen.getByTestId('ack'));
        fireEvent.click(screen.getByTestId('sign-btn'));
        await waitFor(() => expect(screen.getByTestId('sign-progress').dataset.step).toBe('FAILED'));
        expect(screen.getByTestId('sign-progress').textContent).toMatch(/Bạn đã hủy thao tác ký/);
        expect(mock.state.calls.some((c) => c.method === 'POST')).toBe(false);
        expect(signCalls(provider)).toBe(1);
        fireEvent.click(screen.getByTestId('sign-reset'));
        await waitFor(() => expect(screen.queryByTestId('sign-progress')).toBeNull());
        expect(screen.getByTestId('sign-btn').disabled).toBe(false);
    });

    it('gửi chữ ký lỗi mạng: "Gửi lại chữ ký" KHÔNG bật MetaMask lần nữa', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        const real = (code, body) => fetch(`http://localhost:5000/api/disputes/${code}/signatures`, { method: 'POST', body: JSON.stringify({ resolution_id: body.resolutionId, signature: body.signature }) }).then((r) => r.json());
        const send = vi.fn()
            .mockRejectedValueOnce(Object.assign(new Error('Không kết nối được máy chủ'), { code: 'NETWORK_ERROR', status: 0 }))
            .mockImplementation(real);
        const provider = show({ pageProps: { send } });
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        fireEvent.click(screen.getByTestId('ack'));
        fireEvent.click(screen.getByTestId('sign-btn'));
        const resend = await screen.findByTestId('resend');
        expect(signCalls(provider)).toBe(1);
        fireEvent.click(resend);
        await waitFor(() => expect(screen.getByTestId('phase-ready')).toBeTruthy());
        expect(signCalls(provider)).toBe(1); // vẫn một lần ký
        expect(send.mock.calls[1][1].signature).toBe(send.mock.calls[0][1].signature);
    });

    it('bấm ký dồn: chỉ MỘT hộp ký', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        const provider = show();
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        fireEvent.click(screen.getByTestId('ack'));
        const b = screen.getByTestId('sign-btn');
        fireEvent.click(b); fireEvent.click(b); fireEvent.click(b);
        await waitFor(() => expect(screen.getByTestId('phase-ready')).toBeTruthy());
        expect(signCalls(provider)).toBe(1);
    });

    it('đề xuất bị hủy khi đang xem: chữ ký bị máy chủ từ chối (409) được báo, không treo', async () => {
        mock.state.forceRole = 'BUYER';
        mock.state.propose({ payoutTo: 'buyer' });
        show();
        await connect();
        await waitFor(() => expect(screen.queryByTestId('gate-connect')).toBeNull());
        fireEvent.click(screen.getByTestId('ack'));
        mock.state.resolution.status = 'CANCELLED'; // Admin vừa hủy, trang chưa kịp poll
        fireEvent.click(screen.getByTestId('sign-btn'));
        await waitFor(() => expect(screen.queryByTestId('sign-btn') === null || screen.queryByTestId('sign-progress')?.dataset.step === 'FAILED').toBe(true));
        await waitFor(() => expect(screen.getByTestId('phase-cancelled')).toBeTruthy());
    });
});
