import { describe, it, expect } from 'vitest';
import { formatVND } from '../utils/formatVND';

const norm = (s) => s.replace(/\s/g, ' '); // Intl dùng NBSP

describe('formatVND', () => {
  it('định dạng vi-VN, không có phần thập phân và không có $', () => {
    expect(norm(formatVND(1234567))).toBe('1.234.567 ₫');
    expect(norm(formatVND('25000'))).toBe('25.000 ₫');
    expect(formatVND(0)).toContain('0');
    expect(formatVND(1500000)).not.toContain('$');
  });

  it('làm tròn số lẻ và xử lý giá trị không hợp lệ', () => {
    expect(norm(formatVND(99999.6))).toBe('100.000 ₫');
    expect(norm(formatVND(undefined))).toBe('0 ₫');
    expect(norm(formatVND('abc'))).toBe('0 ₫');
  });
});
