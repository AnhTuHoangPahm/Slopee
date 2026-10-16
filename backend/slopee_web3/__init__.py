"""Mô-đun Web3 Escrow của Slopee (SDD 3.3, kiến trúc Hexagonal).

domain/       thực thể + quy tắc thuần, KHÔNG I/O, KHÔNG import ngoài thư viện chuẩn
ports/        giao diện trừu tượng (Clock, Signer, Chain, Repositories)
application/  ca sử dụng (WalletService UC-00, QuoteService UC-01) — chỉ phụ thuộc domain + ports
adapters/     web3.py, MySQL, Flask, Indexer — phụ thuộc cả ba lớp trên

Quy tắc phụ thuộc được test bằng test/unit_test/test_w3_architecture.py (T-ARCH-01).
"""
