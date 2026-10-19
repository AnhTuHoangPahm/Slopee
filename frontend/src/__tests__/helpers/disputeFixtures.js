// Dữ liệu dùng chung cho test màn hình tranh chấp. Khóa dưới đây là KHÓA CÔNG KHAI của Anvil (giống test/w3_support.py), không phải bí mật.
import { Wallet } from 'ethers';

export const KEYS = {
    buyer: '0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba', // #5
    merchant: '0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e', // #6
    arbitrator: '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a', // #2
    stranger: '0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a', // #12
};
export const WALLET = Object.fromEntries(Object.entries(KEYS).map(([k, v]) => [k, new Wallet(v)]));
export const ADDR = Object.fromEntries(Object.entries(WALLET).map(([k, w]) => [k, w.address]));
export const ESCROW = '0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512';
export const DEPLOYMENT = { chainId: 31337, escrow: ESCROW };

export const NOW = 1_800_000_000;

/** Phản hồi GET /api/disputes/:code (xem api/disputes.js) với một đề xuất hoàn tiền cho Buyer, đang PROPOSED. */
export function makeView(over = {}, resOver = {}) {
    return {
        order_id: 'ord-1', onchain_order_id: '100501', order_status: 'DISPUTED', your_party: 'BUYER',
        buyer_wallet: ADDR.buyer, merchant_wallet: ADDR.merchant,
        amount_raw: '25000000', decimals: 6, symbol: 'mUSD', fee_bps: 300,
        disputed_at: NOW - 3600, dispute_timeout: 2592000, server_time: NOW,
        note: { reason: 'Hàng bị vỡ', evidence_url: 'https://example.com/a.jpg', updated_at: NOW - 3000 },
        resolution: {
            resolution_id: 7, payout_to: ADDR.buyer, amount_raw: '25000000', nonce: 0, deadline: NOW + 7 * 86400, status: 'PROPOSED',
            reason_note: 'Đề xuất hoàn tiền', submitted_tx_hash: null, created_at: NOW,
            signatures: [{ party: 'ARBITRATOR', signer: ADDR.arbitrator, signed_at: NOW }], ...resOver,
        },
        ...over,
    };
}
