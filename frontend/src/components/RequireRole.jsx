import { Link, Navigate, useLocation } from 'react-router-dom';
import { getUser } from '../lib/client';

/**
 * Route guard (SDD 9.8). Chưa đăng nhập → /login. Có `roles` mà role không khớp → thông báo không đủ quyền.
 * `roles` là chuỗi hoặc mảng chuỗi; bỏ trống = chỉ cần đã đăng nhập.
 * Đây CHỈ là lớp tiện lợi cho giao diện — quyền thật luôn do backend kiểm tra từ token (P0-01/P0-02).
 */
export default function RequireRole({ roles, children }) {
    const location = useLocation();
    const user = getUser();

    if (!user) {
        return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
    }

    const allowed = roles == null ? null : [].concat(roles);
    if (allowed && !allowed.includes(user.role)) {
        return (
            <div role="alert" style={{ maxWidth: 480, margin: '80px auto', textAlign: 'center' }}>
                <h2>Bạn không có quyền truy cập trang này</h2>
                <p>Tài khoản của bạn không thuộc vai trò được phép.</p>
                <Link to="/">Về trang chủ</Link>
            </div>
        );
    }

    return children;
}
