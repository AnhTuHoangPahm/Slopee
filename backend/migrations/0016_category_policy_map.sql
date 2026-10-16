-- Web3 (SRS 9 bảng 11): gán danh mục sản phẩm của Slopee vào nhóm chính sách, KHÔNG sửa bảng categories (SDD 7.3 #7).
-- Danh mục chưa ánh xạ dùng nhóm GENERAL (xử lý ở backend). categories.id là INT UNSIGNED. SDD 011_category_policy_map.sql -> 0016.
CREATE TABLE IF NOT EXISTS category_policy_map (
    category_id INT UNSIGNED PRIMARY KEY,
    policy_code VARCHAR(32) NOT NULL,
    CONSTRAINT fk_cpm_category FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
    CONSTRAINT fk_cpm_policy FOREIGN KEY (policy_code) REFERENCES category_policies(policy_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
