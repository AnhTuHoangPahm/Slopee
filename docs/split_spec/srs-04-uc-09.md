<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, UC-09 (mục 4). Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# UC-09: Quản trị tham số

- Admin đổi `defaultFeeBps` (trần phí, tối đa 1.000) và `feeRecipient` qua giao dịch từ ví Admin; đổi `PLATFORM_FEE_BPS`, tỷ giá, thời hạn báo giá, thời hạn chữ ký trong `platform_settings`. Mọi thay đổi ghi lại người thực hiện và thời điểm.
- **Quy trình đổi phí:** khi tăng phí, đổi trần trên chuỗi trước rồi mới đổi `PLATFORM_FEE_BPS`; khi hạ phí, đổi `PLATFORM_FEE_BPS` trước rồi hạ trần. Báo giá chưa dùng có phí cao hơn trần mới sẽ bị contract từ chối và Buyer nhận báo giá mới (`FEE_CAP_CHANGED`).
- Admin gán từng danh mục sản phẩm vào một nhóm chính sách (`category_policy_map`); thay đổi chỉ ảnh hưởng đơn mới.
