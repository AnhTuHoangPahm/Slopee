<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 14. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 14. MA TRẬN TRUY VẾT YÊU CẦU

| BRD | Use case | Hàm contract / API chính | Kiểm thử / Nghiệm thu |
|---|---|---|---|
| BR-01 | UC-00, UC-02, UC-06 | Ký ở ví người dùng; khóa sàn ở môi trường | E-05 / AC-09 |
| BR-02 | UC-04, UC-09 | `_executePayout`, `setDefaultFeeBps` | T-08, T-09, T-22 / AC-04, 13 |
| BR-03 | UC-03, UC-04, UC-05 | `confirmDelivery`, `earlyRelease`, `releaseAfterInspection`, `raiseDispute` | T-05 đến T-07, T-10 / AC-03, 04, 05 |
| BR-04 | UC-06 | `resolveDispute`, `_partyOf` | T-11 đến T-13, T-24 / AC-06 |
| BR-05 | UC-07 | `cancelIfUnfulfilled`, `arbitratorForceResolve`, `claimPending` | T-14 đến T-16, T-20, T-21, T-24, I-05 / AC-07, 12 |
| BR-06 | UC-01, UC-02 | `depositEscrow`, `_verifyQuote`, `POST /api/orders` | T-01 đến T-04, T-22, T-23, T-28, T-30, I-02 / AC-02, 13 |
| BR-07 | UC-00 | `/api/wallet/*` | I-01, A-01 đến A-04 / AC-01 |
| BR-08 | UC-01 | Quy đổi trong `POST /api/orders`, `platform_settings` | I-02 / AC-01 |
| BR-09 | UC-08 | Indexer, `chain_events`, `indexer_cursor` | I-03, I-06, E-06 / AC-08, 10 |
| BR-10 | UC-01, UC-06, UC-07 | `category_policies`, `OrderQuote.disputeTimeout`, `arbitratorForceResolve` | T-15, T-20, T-21, I-04 / AC-12 |
| BR-11 | UC-01, UC-02 | `depositEscrowBatch`, `_acceptQuote`, `checkout_groups`, `POST /api/orders` | T-25 đến T-34, I-07, E-07 / AC-14 |
