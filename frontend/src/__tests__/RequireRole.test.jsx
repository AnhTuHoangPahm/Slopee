import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, beforeEach } from 'vitest';
import RequireRole from '../components/RequireRole';
import { setSession, clearSession } from '../lib/client';

const renderAt = (path, roles) =>
    render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/login" element={<div>Trang đăng nhập</div>} />
                <Route path="/secret" element={<RequireRole roles={roles}><div>Nội dung bảo vệ</div></RequireRole>} />
            </Routes>
        </MemoryRouter>,
    );

describe('RequireRole', () => {
    beforeEach(() => {
        sessionStorage.clear();
        clearSession();
    });

    it('chưa đăng nhập → chuyển về /login', () => {
        renderAt('/secret', 'admin');
        expect(screen.getByText('Trang đăng nhập')).toBeDefined();
        expect(screen.queryByText('Nội dung bảo vệ')).toBeNull();
    });

    it('đúng role (chuỗi) → hiện nội dung', () => {
        setSession('t', { id: 'u1', role: 'admin' });
        renderAt('/secret', 'admin');
        expect(screen.getByText('Nội dung bảo vệ')).toBeDefined();
    });

    it('đúng một trong các role (mảng) → hiện nội dung', () => {
        setSession('t', { id: 'u1', role: 'seller' });
        renderAt('/secret', ['seller', 'admin']);
        expect(screen.getByText('Nội dung bảo vệ')).toBeDefined();
    });

    it('sai role → báo không đủ quyền, không hiện nội dung, không đẩy về /login', () => {
        setSession('t', { id: 'u1', role: 'user' });
        renderAt('/secret', 'admin');
        expect(screen.getByRole('alert').textContent).toContain('không có quyền');
        expect(screen.queryByText('Nội dung bảo vệ')).toBeNull();
        expect(screen.queryByText('Trang đăng nhập')).toBeNull();
    });

    it('không chỉ định role → chỉ cần đã đăng nhập', () => {
        setSession('t', { id: 'u1', role: 'user' });
        renderAt('/secret', undefined);
        expect(screen.getByText('Nội dung bảo vệ')).toBeDefined();
    });
});
