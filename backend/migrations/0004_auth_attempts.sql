-- P0-05 (S-09): bảng đếm số lần thử sai mật khẩu/PIN để khóa tạm (xem throttle.py).
-- scope: password hoặc pin. subject: id:<userId> hoặc u:<sha256 username>. lockedUntil: epoch giây (0 = không khóa).
CREATE TABLE IF NOT EXISTS authAttempts (
    scope varchar(16) NOT NULL,
    subject varchar(80) NOT NULL,
    failedCount int NOT NULL DEFAULT 0,
    lockedUntil bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, subject)
);
