#!/usr/bin/env python3
"""Đối soát số dư contract với CSDL (AC-10, G-01, SDD 6.3). Tuần 7, B. CHỈ ĐỌC: không ký, không gửi giao dịch, không sửa dữ liệu.

Bất biến, với mỗi token:
    Σ amount_raw của đơn LOCKED/DELIVERED/DISPUTED  +  Σ PayoutDeferred − Σ PendingClaimed  ==  balanceOf(contract)   (ETH: eth_getBalance)

Số dư contract được đọc TẠI ĐÚNG block Indexer đã xử lý xong và dữ liệu MySQL đọc trong MỘT snapshot với con trỏ, nên Indexer trễ không gây báo
lệch giả. Dùng được cho CI/cron/kịch bản demo: kết quả nằm ở MÃ THOÁT chứ không chỉ ở chữ in ra.

    python scripts/reconcile.py                 # đối soát số dư (mặc định)
    python scripts/reconcile.py --deep          # + so trạng thái từng đơn mở với contract (chỉ khi Indexer đã bắt kịp)
    python scripts/reconcile.py --events        # + nguồn thứ ba: dựng lại số tiền từ chain_events, không qua handler của Indexer
    python scripts/reconcile.py --wait 30       # đợi tối đa 30 giây cho Indexer bắt kịp trước khi đối soát (dùng sau một kịch bản)
    python scripts/reconcile.py --json          # kết quả máy đọc được (số tiền là CHUỖI, uint256 vượt giới hạn số của JSON)
    python scripts/reconcile.py --strict        # đơn bị gắn anomaly_flag cũng tính là lỗi

Mã thoát:  0 = khớp   |   1 = LỆCH (hoặc --strict và có cảnh báo anomaly)   |   2 = không chạy được (chưa cấu hình Web3, mất kết nối DB/RPC,
Indexer chưa chạy lần nào).  Cần backend/.env + backend/.env.web3 (scripts/bootstrap.sh sinh) và MySQL đã migrate; KHÔNG cần khóa riêng.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, 'backend')

EXIT_OK, EXIT_MISMATCH, EXIT_ERROR = 0, 1, 2


def build_service():
    """Dựng ReconcileService từ môi trường (cùng cách Indexer/Scheduler dựng). Ném RuntimeError với thông điệp tiếng Việt nếu thiếu cấu hình."""
    from dotenv import load_dotenv
    for name in ('.env', '.env.web3'):
        load_dotenv(os.path.join(BACKEND, name))
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from routes.auth import get_db_connection
    from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
    from slopee_web3.adapters.web3_chain import Web3Chain
    from slopee_web3.application.reconcile_service import ReconcileService
    from slopee_web3.settings import Web3Settings
    s = Web3Settings.from_env()
    if s is None:
        raise RuntimeError('Chưa cấu hình Web3: chạy scripts/bootstrap.sh để sinh backend/.env.web3')
    chain = Web3Chain(s.rpc_url, s.escrow_address, timeout=s.rpc_timeout)
    return ReconcileService(lambda: MySqlUnitOfWork(get_db_connection), chain, known_tokens=[s.token_address], confirmations=s.confirmations)


def run_checks(service, *, deep=False, events=False, wait=0.0, sleep=time.sleep, clock=time.monotonic, poll=1.0):
    """Chạy đối soát; nếu `wait` > 0 thì lặp tới khi Indexer bắt kịp (lag = 0) hoặc hết giờ. Trả kết quả của lần chạy cuối."""
    deadline = clock() + max(0.0, float(wait))
    while True:
        result = service.run(deep=deep, events=events)
        caught_up = result['indexer_lag_blocks'] == 0
        if caught_up or clock() >= deadline:
            return result
        sleep(poll)


def exit_code(result, strict=False):
    if result['indexer_cursor_missing']:
        return EXIT_ERROR                  # chưa có con trỏ: Indexer chưa chạy lần nào, không có gì để đối chiếu
    if not result['ok'] or (strict and result['anomalies']):
        return EXIT_MISMATCH
    return EXIT_OK


def _short(token):
    return token if token == 'ETH' else f"{token[:8]}…{token[-4:]}"


def format_report(result, strict=False):
    """Báo cáo đọc được (tiếng Việt). Số tiền là đơn vị nhỏ nhất của token (amount_raw)."""
    L = []
    if result['indexer_cursor_missing']:
        return 'KHÔNG ĐỐI SOÁT ĐƯỢC: Indexer chưa chạy lần nào (chưa có con trỏ). Chạy `python -m slopee_web3.adapters.indexer --once` trước.'
    lag = result['indexer_lag_blocks']
    L.append(f"Đối soát tại block {result['checked_at_block']} (mới nhất {result['latest_block']}, Indexer trễ {lag} block)")
    L.append('')
    L.append(f"{'Token':<16}{'Đơn mở':>7}{'Σ đơn mở':>22}{'Chờ rút':>16}{'Kỳ vọng':>22}{'Số dư contract':>22}{'Lệch':>12}  ")
    for t in result['tokens']:
        L.append(f"{_short(t['token']):<16}{t['open_orders']:>7}{t['open_orders_raw']:>22}{t['pending_raw']:>16}{t['expected_raw']:>22}"
                 f"{t['balance_raw']:>22}{t['diff_raw']:>12}  {'OK' if t['ok'] else '<-- LỆCH'}")
        if not t['ok']:
            direction = 'contract DƯ tiền so với đơn mở (tiền vào ngoài luồng đơn hoặc sự kiện bị bỏ sót)' if int(t['diff_raw']) > 0 else \
                'contract THIẾU tiền so với đơn mở (tiền ra ngoài luồng đơn hoặc lỗi contract): NGHIÊM TRỌNG'
            L.append(f"    {direction}")
    mm = result['order_mismatches']
    if mm is None and result.get('order_mismatches_requested'):
        L.append('')
        L.append('Bỏ qua so từng đơn: Indexer chưa bắt kịp (orders(id) chỉ đọc được ở block mới nhất).')
    for m in mm or []:
        L.append(f"  đơn on-chain {m['onchain_order_id']}: CSDL={m['db_status']} nhưng contract={m['chain_state']}")
    if result.get('event_drift') is not None:
        L.append('')
        drift, order_drift = result['event_drift'], result.get('event_order_drift') or []
        if drift or order_drift:
            L.append('NGUỒN SỰ KIỆN LỆCH VỚI order_web3 (handler của Indexer áp sai?):')
        else:
            L.append('Nguồn sự kiện (chain_events) khớp order_web3.')
        for d in drift:
            L.append(f"  {_short(d['token'])} {d['field']}: order_web3={d['db_raw']} chain_events={d['events_raw']}")
        for d in order_drift:
            L.append(f"  đơn on-chain {d['onchain_order_id']}: order_web3 coi là {'ĐANG MỞ' if d['db_open'] else 'ĐÃ ĐÓNG'} "
                     f"nhưng sự kiện cho thấy {'ĐANG MỞ' if d['events_open'] else 'ĐÃ ĐÓNG'}")
    if result['anomalies']:
        L.append('')
        L.append(f"CẢNH BÁO: {len(result['anomalies'])} đơn bị gắn anomaly_flag (sàn không tự sửa, Admin phải xem):")
        for a in result['anomalies'][:20]:
            L.append(f"  đơn {a['order_id']} (on-chain {a['onchain_order_id']}, {a['status']})")
    L.append('')
    verdict = 'KHỚP' if exit_code(result, strict) == EXIT_OK else 'LỆCH'
    L.append(f"KẾT QUẢ: {verdict}")
    return '\n'.join(L)


def main(argv=None, service=None, out=None, err=None, sleep=time.sleep):
    out, err = out or sys.stdout, err or sys.stderr
    p = argparse.ArgumentParser(description='Đối soát số dư contract với CSDL (AC-10). Chỉ đọc.')
    p.add_argument('--deep', action='store_true', help='so thêm trạng thái từng đơn mở với contract')
    p.add_argument('--events', action='store_true', help='so thêm với số tiền dựng lại từ chain_events')
    p.add_argument('--wait', type=float, default=0.0, metavar='GIÂY', help='đợi Indexer bắt kịp tối đa chừng này giây')
    p.add_argument('--json', action='store_true', help='in JSON thay cho báo cáo')
    p.add_argument('--strict', action='store_true', help='đơn có anomaly_flag cũng tính là lỗi (mã thoát 1)')
    args = p.parse_args(argv)
    try:
        service = service or build_service()
        result = run_checks(service, deep=args.deep, events=args.events, wait=args.wait, sleep=sleep)
    except Exception as e:      # noqa: BLE001 - DB/RPC/cấu hình: một mã thoát riêng để cron phân biệt "lệch" với "không chạy được"
        print(f'LỖI: không đối soát được: {type(e).__name__}: {e}', file=err)
        return EXIT_ERROR
    result['order_mismatches_requested'] = args.deep
    code = exit_code(result, args.strict)
    if args.json:
        result['exit_code'] = code
        print(json.dumps(result, ensure_ascii=False, indent=2), file=out)
    else:
        print(format_report(result, args.strict), file=out)
    return code


if __name__ == '__main__':
    sys.exit(main())
