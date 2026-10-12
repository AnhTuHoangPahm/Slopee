// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./EscrowBase.t.sol";
import "./TestActors.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";

/// @notice Handler cho invariant test (T-18, T-33). Mỗi hành động gọi một hàm của contract với tham số ngẫu nhiên đã giới hạn;
///         lời gọi sai trạng thái/sai quyền cố tình được gửi đi (try/catch) để chứng minh chúng không phá bất biến.
///         Handler kế thừa `EscrowBase` để dùng lại helper ký báo giá/phán quyết; nó KHÔNG gọi `setUp` của Base.
contract EscrowHandler is EscrowBase {
    bytes32 internal constant SIG_CREATED =
        keccak256("OrderCreated(uint256,address,address,address,uint256,uint256,uint256,bytes32,uint256)");
    bytes32 internal constant SIG_COMPLETED = keccak256("OrderCompleted(uint256,uint256,uint256)");

    // ---- Trạng thái ghi nhận để kiểm bất biến
    uint256[] internal _ids;
    mapping(uint256 => uint256) public quotedFee;      // phí trong báo giá đã ký (INV-06)
    mapping(uint256 => uint256) public capAtDeposit;   // trần phí tại lúc gửi giao dịch nạp (INV-07)
    mapping(uint256 => uint8) public terminalState;    // trạng thái cuối đã thấy (INV-02), 0 = chưa kết thúc
    mapping(uint256 => uint256) public lastNonce;      // nonce lớn nhất đã thấy (INV-04)
    mapping(uint256 => uint256) public createdEvents;  // số sự kiện OrderCreated theo mã đơn (INV-05)
    bool public feeSplitViolated;                      // INV-03
    bool public terminalChanged;                       // INV-02
    bool public nonceDecreased;                        // INV-04

    address[] internal _holders;                       // mọi địa chỉ có thể có khoản chờ rút
    address[] internal _merchants;
    SmartWallet public wallet;                         // Merchant/nơi nhận phí bật tắt được việc nhận ETH
    address public otherFeeRecipient;

    // ---- Thống kê để chứng minh handler thật sự chạm tới các nhánh (in ra khi cần)
    uint256 public nDeposits;
    uint256 public nBatchDeposits;
    uint256 public nCompleted;
    uint256 public nRefunded;
    uint256 public nDisputed;
    uint256 public nResolved;
    uint256 public nForced;
    uint256 public nDeferred;
    uint256 public nClaims;

    constructor(SlopeeEscrowMaster _escrow, MockUSD _usd) {
        escrow = _escrow;
        usd = _usd;
        admin = vm.addr(ADMIN_KEY);
        shipper = vm.addr(SHIPPER_KEY);
        arbitrator = vm.addr(ARBITRATOR_KEY);
        signer = vm.addr(SIGNER_KEY);
        feeRecipient = vm.addr(FEE_KEY);
        buyer = vm.addr(BUYER_KEY);
        merchant = vm.addr(MERCHANT_KEY);

        wallet = new SmartWallet(false); // mặc định từ chối ETH ⇒ khoản bị hoãn vào sổ chờ rút, rồi `toggleWallet` + `claim` rút ra
        otherFeeRecipient = makeAddr("otherFeeRecipient");

        _merchants.push(merchant);
        _merchants.push(makeAddr("shopA"));
        _merchants.push(makeAddr("shopB"));
        _merchants.push(address(wallet));

        _holders.push(buyer);
        _holders.push(feeRecipient);
        _holders.push(otherFeeRecipient);
        _holders.push(address(wallet));
        for (uint256 i = 0; i < _merchants.length; i++) {
            if (_merchants[i] != address(wallet)) _holders.push(_merchants[i]);
        }
        nextId = 1_000;
    }

    // `setUp` thừa kế từ EscrowBase sẽ tạo escrow mới; khóa lại để không trở thành hành động ngẫu nhiên.
    function setUp() public pure override {
        revert("handler: setUp unused");
    }

    // ------------------------------------------------------------------ Truy vấn cho test invariant

    function idsLength() external view returns (uint256) { return _ids.length; }
    function idAt(uint256 i) external view returns (uint256) { return _ids[i]; }
    function holdersLength() external view returns (uint256) { return _holders.length; }
    function holderAt(uint256 i) external view returns (address) { return _holders[i]; }

    // ------------------------------------------------------------------ Nội bộ

    modifier tracked() {
        vm.recordLogs();
        _;
        _afterAction();
    }

    function _pick(uint256 sel) internal view returns (bool ok, uint256 id) {
        if (_ids.length == 0) return (false, 0);
        return (true, _ids[sel % _ids.length]);
    }

    function _orderState(uint256 id) internal view returns (SlopeeEscrowMaster.OrderState st) {
        (, , , , , , , , , , st, ) = escrow.orders(id);
    }

    /// @dev Ghi nhận mã đơn mới; đọc sự kiện để đếm OrderCreated / kiểm chia phí; cập nhật trạng thái cuối và nonce.
    function _afterAction() internal {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].emitter != address(escrow) || logs[i].topics.length == 0) continue;
            if (logs[i].topics[0] == SIG_CREATED) {
                createdEvents[uint256(logs[i].topics[1])]++;
            } else if (logs[i].topics[0] == SIG_COMPLETED) {
                uint256 id = uint256(logs[i].topics[1]);
                (uint256 net, uint256 fee) = abi.decode(logs[i].data, (uint256, uint256));
                (, , , uint256 amount, , , , , , uint256 feeBps, , ) = escrow.orders(id);
                if (net + fee != amount || fee != (amount * feeBps) / 10000) feeSplitViolated = true;
            } else if (logs[i].topics[0] == keccak256("PayoutDeferred(address,address,uint256)")) {
                nDeferred++;
            }
        }
        for (uint256 i = 0; i < _ids.length; i++) {
            uint256 id = _ids[i];
            uint8 st = uint8(_orderState(id));
            uint8 term = terminalState[id];
            if (term != 0 && st != term) terminalChanged = true;
            if (term == 0 && (st == uint8(SlopeeEscrowMaster.OrderState.COMPLETED) || st == uint8(SlopeeEscrowMaster.OrderState.REFUNDED))) {
                terminalState[id] = st;
                if (st == uint8(SlopeeEscrowMaster.OrderState.COMPLETED)) nCompleted++; else nRefunded++;
            }
            uint256 n = escrow.disputeNonces(id);
            if (n < lastNonce[id]) nonceDecreased = true;
            lastNonce[id] = n;
        }
    }

    function _newQuote(address token, uint256 amount, uint256 feeBps, uint256 merchSel, uint256 inspSel, uint256 tmoSel, bool reuse, uint256 reuseSel)
        internal
        returns (SlopeeEscrowMaster.Quote memory q)
    {
        q = _quote(token, amount);
        q.merchant = _merchants[merchSel % _merchants.length];
        q.feeBps = feeBps;
        q.inspectionDuration = 1 hours + (inspSel % (30 days - 1 hours + 1)); // có thể chạm biên
        q.disputeTimeout = 7 days + (tmoSel % (90 days - 7 days + 1));
        if (reuse && _ids.length > 0) q.orderId = _ids[reuseSel % _ids.length]; // thử nạp trùng mã đơn
    }

    function createdEventsOrState(uint256 id) internal view returns (bool) {
        for (uint256 i = 0; i < _ids.length; i++) if (_ids[i] == id) return true;
        return false;
    }

    // ------------------------------------------------------------------ Hành động: nạp tiền

    function depositSingle(uint256 amount, uint256 feeBps, uint256 merchSel, uint256 inspSel, uint256 tmoSel, bool useEth, bool reuse, uint256 reuseSel)
        external
        tracked
    {
        amount = bound(amount, 1, useEth ? 5 ether : 10_000e6);
        uint256 cap = escrow.defaultFeeBps();
        feeBps = feeBps % 10 == 0 ? cap + 1 : feeBps % (cap + 1); // ~10% vượt trần để thử bị từ chối
        reuse = reuse && reuseSel % 4 == 0;                       // ~12% nạp trùng mã đơn
        address token = useEth ? address(0) : address(usd);
        SlopeeEscrowMaster.Quote memory q = _newQuote(token, amount, feeBps, merchSel, inspSel, tmoSel, reuse, reuseSel);
        bool existed = createdEventsOrState(q.orderId);
        bytes memory sig = _signQuote(q);
        if (useEth) vm.deal(buyer, buyer.balance + amount); else usd.mint(buyer, amount);
        vm.prank(buyer);
        try escrow.depositEscrow{value: useEth ? amount : 0}(q, sig) {
            nDeposits++;
            if (!existed) { quotedFee[q.orderId] = q.feeBps; capAtDeposit[q.orderId] = cap; _ids.push(q.orderId); }
        } catch {}
    }

    function depositBatch(uint256 n, uint256 amount, uint256 feeBps, uint256 merchSel, uint256 inspSel, uint256 tmoSel, bool useEth, uint256 dupSel)
        external
        tracked
    {
        n = n % 12 == 0 ? 6 : 1 + (n % 5); // thỉnh thoảng 6 > MAX_BATCH_SIZE để thử "Invalid batch size"
        amount = bound(amount, 1, useEth ? 2 ether : 5_000e6);
        uint256 capNow = escrow.defaultFeeBps();
        feeBps = feeBps % 12 == 0 ? capNow + 1 : feeBps % (capNow + 1);
        bool dupInside = dupSel % 8 == 0;
        address token = useEth ? address(0) : address(usd);

        SlopeeEscrowMaster.Quote[] memory qs = new SlopeeEscrowMaster.Quote[](n);
        bytes[] memory sigs = new bytes[](n);
        uint256 total;
        for (uint256 i = 0; i < n; i++) {
            qs[i] = _newQuote(token, amount + i, feeBps, merchSel + i, inspSel + i, tmoSel + i, false, 0);
            if (dupInside && i == 1) qs[i].orderId = qs[0].orderId; // trùng mã đơn trong cùng lô (T-27)
            total += qs[i].amount;
        }
        uint256 cap = capNow;
        for (uint256 i = 0; i < n; i++) sigs[i] = _signQuote(qs[i]);
        if (useEth) vm.deal(buyer, buyer.balance + total); else usd.mint(buyer, total);

        vm.prank(buyer);
        try escrow.depositEscrowBatch{value: useEth ? total : 0}(qs, sigs) {
            nBatchDeposits++;
            for (uint256 i = 0; i < n; i++) {
                if (!createdEventsOrState(qs[i].orderId)) {
                    quotedFee[qs[i].orderId] = qs[i].feeBps;
                    capAtDeposit[qs[i].orderId] = cap;
                    _ids.push(qs[i].orderId);
                }
            }
        } catch {}
    }

    // ------------------------------------------------------------------ Hành động: vòng đời đơn

    function deliver(uint256 sel) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        vm.prank(shipper);
        try escrow.confirmDelivery(id) {} catch {}
    }

    function earlyRelease(uint256 sel) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        vm.prank(buyer);
        try escrow.earlyRelease(id) {} catch {}
    }

    function releaseAfterInspection(uint256 sel, bool warpFirst) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        if (warpFirst) {
            (, , , , , uint256 deliveredAt, , , uint256 insp, , , ) = escrow.orders(id);
            if (deliveredAt != 0 && block.timestamp < deliveredAt + insp) vm.warp(deliveredAt + insp);
        }
        try escrow.releaseAfterInspection(id) {} catch {}
    }

    function cancelIfUnfulfilled(uint256 sel, bool warpFirst, bool byAdmin) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        if (warpFirst) {
            (, , , , uint256 createdAt, , , , , , , ) = escrow.orders(id);
            if (block.timestamp < createdAt + 14 days) vm.warp(createdAt + 14 days);
        }
        vm.prank(byAdmin ? admin : buyer);
        try escrow.cancelIfUnfulfilled(id) {} catch {}
    }

    function raiseDispute(uint256 sel) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        vm.prank(buyer);
        try escrow.raiseDispute(id) { nDisputed++; } catch {}
    }

    /// @param pair 0: Trọng tài+Buyer, 1: Trọng tài+Merchant(có khóa), 2: Buyer+Merchant(có khóa), 3: Buyer+Buyer (phải bị từ chối)
    function resolveDispute(uint256 sel, bool toBuyer, uint256 pair, uint256 deadlineDelta, bool wrongAmount) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        (address b, address m, , uint256 amount, , , , , , , , ) = escrow.orders(id);
        address payoutTo = toBuyer ? b : m;
        uint256 deadline = block.timestamp + bound(deadlineDelta, 0, 20 days);
        uint256 signedAmount = wrongAmount ? amount + 1 : amount;
        pair = pair % 4;
        uint256 k1 = pair == 0 ? ARBITRATOR_KEY : pair == 1 ? ARBITRATOR_KEY : pair == 2 ? BUYER_KEY : BUYER_KEY;
        uint256 k2 = pair == 0 ? BUYER_KEY : pair == 1 ? MERCHANT_KEY : pair == 2 ? MERCHANT_KEY : BUYER_KEY;
        (bytes memory s1, bytes memory s2) = _twoSigs(k1, k2, id, payoutTo, signedAmount, deadline);
        try escrow.resolveDispute(id, payoutTo, deadline, s1, s2) { nResolved++; } catch {}
    }

    function forceResolve(uint256 sel, bool toBuyer, bool warpFirst) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        (address b, address m, , , , , uint256 disputedAt, uint256 tmo, , , , ) = escrow.orders(id);
        if (warpFirst && disputedAt != 0 && block.timestamp < disputedAt + tmo) vm.warp(disputedAt + tmo);
        address payoutTo = toBuyer ? b : m;
        vm.prank(arbitrator);
        try escrow.arbitratorForceResolve(id, payoutTo) { nForced++; } catch {}
    }

    // ------------------------------------------------------------------ Hành động: sổ chờ rút, quản trị, thời gian

    function claim(uint256 holderSel, bool eth) external tracked {
        address holder = holderSel % 2 == 0 ? address(wallet) : _holders[holderSel % _holders.length];
        address token = eth ? address(0) : address(usd);
        if (holder == address(wallet) && holderSel % 8 == 0) wallet.setAccept(true); // ví nhận lại ETH rồi mới rút
        if (holder == address(wallet)) {
            try wallet.exec(address(escrow), abi.encodeWithSelector(escrow.claimPending.selector, token)) { nClaims++; } catch {}
        } else {
            vm.prank(holder);
            try escrow.claimPending(token) { nClaims++; } catch {}
        }
    }

    function toggleWallet(bool accept) external tracked {
        wallet.setAccept(accept);
    }

    function setCeiling(uint256 newCap) external tracked {
        newCap = bound(newCap, 0, 1100); // vượt 1000 để thử bị từ chối
        vm.prank(admin);
        try escrow.setDefaultFeeBps(newCap) {} catch {}
    }

    function setFeeRecipient(uint256 sel) external tracked {
        address[3] memory options = [feeRecipient, otherFeeRecipient, address(wallet)];
        vm.prank(admin);
        try escrow.setFeeRecipient(options[sel % 3]) {} catch {}
    }

    /// @dev Đẩy một đơn sang bước hợp lệ kế tiếp để chuỗi ngẫu nhiên đi sâu vào vòng đời (giao, khiếu nại, giải ngân, phân xử, thoát hiểm).
    function progress(uint256 sel, uint256 choice) external tracked {
        (bool ok, uint256 id) = _pick(sel);
        if (!ok) return;
        SlopeeEscrowMaster.OrderState st = _orderState(id);
        (address b, address m, , uint256 amount, uint256 createdAt, uint256 deliveredAt, uint256 disputedAt, uint256 tmo, uint256 insp, , , ) = escrow.orders(id);
        if (st == SlopeeEscrowMaster.OrderState.LOCKED) {
            if (choice % 6 == 0) {
                if (block.timestamp < createdAt + 14 days) vm.warp(createdAt + 14 days);
                vm.prank(buyer);
                try escrow.cancelIfUnfulfilled(id) {} catch {}
            } else {
                vm.prank(shipper);
                try escrow.confirmDelivery(id) {} catch {}
            }
        } else if (st == SlopeeEscrowMaster.OrderState.DELIVERED) {
            if (choice % 4 < 2) {
                vm.prank(buyer);
                try escrow.raiseDispute(id) { nDisputed++; } catch {}
            } else if (choice % 4 == 2) {
                vm.prank(buyer);
                try escrow.earlyRelease(id) {} catch {}
            } else {
                if (block.timestamp < deliveredAt + insp) vm.warp(deliveredAt + insp);
                try escrow.releaseAfterInspection(id) {} catch {}
            }
        } else if (st == SlopeeEscrowMaster.OrderState.DISPUTED) {
            address payoutTo = choice % 2 == 0 ? b : m;
            if (choice % 4 < 2) {
                uint256 deadline = disputedAt + tmo - 1; // hạn chữ ký lớn nhất hợp lệ
                if (block.timestamp > deadline) { return; }
                (bytes memory s1, bytes memory s2) = _twoSigs(ARBITRATOR_KEY, BUYER_KEY, id, payoutTo, amount, deadline);
                try escrow.resolveDispute(id, payoutTo, deadline, s1, s2) { nResolved++; } catch {}
            } else {
                if (block.timestamp < disputedAt + tmo) vm.warp(disputedAt + tmo);
                vm.prank(arbitrator);
                try escrow.arbitratorForceResolve(id, payoutTo) { nForced++; } catch {}
            }
        }
    }

    /// @dev Dựng sẵn một đơn ở trạng thái DISPUTED (nạp → giao → khiếu nại) để chuỗi ngẫu nhiên thường xuyên chạm tới phân xử/thoát hiểm.
    function openDispute(uint256 amount, uint256 merchSel, uint256 inspSel, uint256 tmoSel, bool useEth) external tracked {
        amount = bound(amount, 1, useEth ? 2 ether : 5_000e6);
        address token = useEth ? address(0) : address(usd);
        uint256 cap = escrow.defaultFeeBps();
        SlopeeEscrowMaster.Quote memory q = _newQuote(token, amount, cap, merchSel, inspSel, tmoSel, false, 0);
        bytes memory sig = _signQuote(q);
        if (useEth) vm.deal(buyer, buyer.balance + amount); else usd.mint(buyer, amount);
        vm.prank(buyer);
        try escrow.depositEscrow{value: useEth ? amount : 0}(q, sig) {
            nDeposits++;
            quotedFee[q.orderId] = q.feeBps;
            capAtDeposit[q.orderId] = cap;
            _ids.push(q.orderId);
            vm.prank(shipper);
            try escrow.confirmDelivery(q.orderId) {} catch { return; }
            vm.prank(buyer);
            try escrow.raiseDispute(q.orderId) { nDisputed++; } catch {}
        } catch {}
    }

    function advance(uint256 delta) external tracked {
        vm.warp(block.timestamp + bound(delta, 1, 2 days)); // bước nhỏ để các cửa sổ thời gian còn "mở" thường xuyên
    }
}

/// @notice T-18 / T-33: invariant với handler gọi ngẫu nhiên cả `depositEscrow` lẫn `depositEscrowBatch`.
///         Chứng minh INV-01 … INV-07 (SDD 4.6, 4.8) cho mọi chuỗi hành động hợp lệ hoặc cố tình sai.
contract SlopeeEscrowInvariantTest is StdInvariant, EscrowBase {
    EscrowHandler internal handler;

    function setUp() public override {
        super.setUp();
        handler = new EscrowHandler(escrow, usd);
        // handler đóng vai Buyer nên cần quyền chi tiêu token của chính Buyer: Base đã cấp cho `buyer`, cùng địa chỉ với handler.buyer
        targetContract(address(handler));
        bytes4[] memory sels = new bytes4[](16);
        sels[0] = EscrowHandler.depositSingle.selector;
        sels[1] = EscrowHandler.depositBatch.selector;
        sels[2] = EscrowHandler.deliver.selector;
        sels[3] = EscrowHandler.earlyRelease.selector;
        sels[4] = EscrowHandler.releaseAfterInspection.selector;
        sels[5] = EscrowHandler.cancelIfUnfulfilled.selector;
        sels[6] = EscrowHandler.raiseDispute.selector;
        sels[7] = EscrowHandler.resolveDispute.selector;
        sels[8] = EscrowHandler.forceResolve.selector;
        sels[9] = EscrowHandler.claim.selector;
        sels[10] = EscrowHandler.toggleWallet.selector;
        sels[11] = EscrowHandler.setCeiling.selector;
        sels[12] = EscrowHandler.advance.selector;
        sels[13] = EscrowHandler.setFeeRecipient.selector;
        sels[14] = EscrowHandler.progress.selector;
        sels[15] = EscrowHandler.openDispute.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: sels}));
    }

    // ------------------------------------------------------------------ INV-01 / T-18

    function _openAmount(address token) internal view returns (uint256 sum) {
        for (uint256 i = 0; i < handler.idsLength(); i++) {
            uint256 id = handler.idAt(i);
            (, , address t, uint256 amount, , , , , , , SlopeeEscrowMaster.OrderState st, ) = escrow.orders(id);
            if (t != token) continue;
            if (st == SlopeeEscrowMaster.OrderState.LOCKED || st == SlopeeEscrowMaster.OrderState.DELIVERED || st == SlopeeEscrowMaster.OrderState.DISPUTED) {
                sum += amount;
            }
        }
    }

    function _pendingSum(address token) internal view returns (uint256 sum) {
        for (uint256 i = 0; i < handler.holdersLength(); i++) {
            sum += escrow.pendingWithdrawals(token, handler.holderAt(i));
        }
    }

    /// @dev INV-01, T-18: số dư contract (theo từng token) = tổng đơn chưa kết thúc + tổng sổ chờ rút.
    function invariant_INV01_balanceEqualsOpenOrdersPlusPending_token() public view {
        assertEq(usd.balanceOf(address(escrow)), _openAmount(address(usd)) + _pendingSum(address(usd)));
    }

    function invariant_INV01_balanceEqualsOpenOrdersPlusPending_eth() public view {
        assertEq(address(escrow).balance, _openAmount(address(0)) + _pendingSum(address(0)));
    }

    // ------------------------------------------------------------------ INV-02

    function invariant_INV02_terminalStatesNeverChange() public view {
        assertFalse(handler.terminalChanged(), "COMPLETED/REFUNDED da bi doi trang thai");
        for (uint256 i = 0; i < handler.idsLength(); i++) {
            uint256 id = handler.idAt(i);
            uint8 term = handler.terminalState(id);
            if (term != 0) {
                (, , , , , , , , , , SlopeeEscrowMaster.OrderState st, ) = escrow.orders(id);
                assertEq(uint8(st), term);
            }
        }
    }

    // ------------------------------------------------------------------ INV-03

    function invariant_INV03_feeSplitConservesAmount() public view {
        assertFalse(handler.feeSplitViolated(), "net + fee != amount hoac fee != floor(amount*feeBps/10000)");
    }

    // ------------------------------------------------------------------ INV-04

    function invariant_INV04_disputeNonceNeverDecreases() public view {
        assertFalse(handler.nonceDecreased(), "disputeNonces giam");
    }

    // ------------------------------------------------------------------ INV-05

    function invariant_INV05_eachOrderIdDepositedAtMostOnce() public view {
        for (uint256 i = 0; i < handler.idsLength(); i++) {
            assertLe(handler.createdEvents(handler.idAt(i)), 1, "mot ma don duoc nap nhieu lan");
        }
    }

    // ------------------------------------------------------------------ INV-06 / INV-07

    function invariant_INV06_orderFeeEqualsQuotedFee_andINV07_withinCeilingAtDeposit() public view {
        for (uint256 i = 0; i < handler.idsLength(); i++) {
            uint256 id = handler.idAt(i);
            (, , , , , , , , , uint256 fee, SlopeeEscrowMaster.OrderState st, ) = escrow.orders(id);
            if (st == SlopeeEscrowMaster.OrderState.NONE) continue;
            assertEq(fee, handler.quotedFee(id), "feeBps doi so voi bao gia (INV-06)");
            assertLe(fee, handler.capAtDeposit(id), "feeBps vuot tran luc nap (INV-07)");
        }
    }

    // ------------------------------------------------------------------ Mọi tiền đều có chỗ về

    /// @dev Hệ quả tổng hợp: tổng ghi nhận nội bộ của contract không bao giờ vượt số dư thật (không "tạo" nghĩa vụ thiếu tiền).
    function invariant_contractAlwaysSolvent() public view {
        assertGe(usd.balanceOf(address(escrow)), _openAmount(address(usd)));
        assertGe(address(escrow).balance, _openAmount(address(0)));
    }
}
