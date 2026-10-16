import { describe, it, expect } from 'vitest';
import { formatVND, shortAddress } from '../lib/format';
import { formatVND as legacyFormatVND } from '../utils/formatVND';

describe('lib/format', () => {
    it('utils/formatVND vẫn là cùng một hàm (không có hai nguồn sự thật)', () => {
        expect(legacyFormatVND).toBe(formatVND);
    });

    it('shortAddress rút gọn địa chỉ hợp lệ', () => {
        expect(shortAddress('0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc')).toBe('0x9965…A4dc');
    });

    it('shortAddress giữ nguyên giá trị không phải địa chỉ', () => {
        expect(shortAddress('abc')).toBe('abc');
        expect(shortAddress(undefined)).toBe('');
        expect(shortAddress(null)).toBe('');
    });
});
