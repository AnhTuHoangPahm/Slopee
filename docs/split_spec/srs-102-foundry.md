<!-- Nguồn: SRS-SLOPEE-MVP-01 v5.3, mục 10.2. Sinh bởi scripts/split_spec.py từ srs-v5_3.html. ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->

# 10.2. Cấu hình Foundry (foundry.toml)

```text
[profile.default]
src = "src"
out = "out"
test = "test"
libs = ["lib"]
solc_version = "0.8.20"
optimizer = true
optimizer_runs = 200
via_ir = true
remappings = [
  "@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/"
]
```

```bash
# Cài thư viện (khóa phiên bản OpenZeppelin để khớp solc 0.8.20)
forge install foundry-rs/forge-std
forge install OpenZeppelin/openzeppelin-contracts@v5.0.2

forge build
forge test -vvv --gas-report
forge coverage            # mục tiêu từ 90% dòng lệnh
anvil --block-time 2      # chainId 31337, block đều đặn để đồng hồ chuỗi không bị kẹt
```

- `via_ir = true` xử lý lỗi "stack too deep" với struct nhiều trường (`Order`, `Quote`); đổi lại thời gian biên dịch lâu hơn, nên chỉ chạy `forge build` đầy đủ khi cần.
- Cần khóa phiên bản OpenZeppelin (ví dụ v5.0.2) vì một số bản mới hơn yêu cầu trình biên dịch cao hơn 0.8.20; nếu nâng OpenZeppelin thì nâng `solc_version` tương ứng và chạy lại toàn bộ test.
- Trong test dùng `vm.warp` để tua thời gian; trong kiểm thử tích hợp trên Anvil dùng `evm_increaseTime` rồi `evm_mine`.
