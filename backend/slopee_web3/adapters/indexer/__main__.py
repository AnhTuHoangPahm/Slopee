"""Chạy Indexer như một tiến trình riêng (khác tiến trình Flask). Cần backend/.env.web3 (bootstrap.sh sinh) và MySQL.

    python -m slopee_web3.adapters.indexer                  # chạy liên tục
    python -m slopee_web3.adapters.indexer --once           # một vòng rồi thoát
    python -m slopee_web3.adapters.indexer --from-block 0 --reset [--yes] [--dry-run] [--no-verify] [--report FILE] [--json]
                                                            # REPLAY (SDD 6.3, AC-08): xóa dữ liệu dẫn xuất, dựng lại từ log on-chain, so ảnh trước/sau

Mã thoát của chế độ replay:  0 = dựng lại xong và khớp 100%  |  1 = dựng lại xong nhưng KHÁC ảnh trước reset  |  2 = không chạy được
(thiếu cấu hình, Indexer khác đang chạy, mất RPC/DB, chưa xác nhận). Replay giữ khóa Indexer nên không chạy chung với Indexer đang chạy.
"""
import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

EXIT_OK, EXIT_DIFFERENT, EXIT_ERROR = 0, 1, 2


def build_parser():
    p = argparse.ArgumentParser(prog='python -m slopee_web3.adapters.indexer', description='Slopee Indexer')
    p.add_argument('--once', action='store_true', help='chạy một vòng rồi thoát (dùng cho test/gỡ lỗi)')
    p.add_argument('--from-block', type=int, default=None, metavar='N',
                   help='REPLAY từ block N (0 = từ đầu). Chỉ chạy cùng --reset')
    p.add_argument('--reset', action='store_true',
                   help='xóa chain_events từ block N, đặt lại các cột dẫn xuất của order_web3/orders rồi dựng lại từ chuỗi (cần --from-block)')
    p.add_argument('--yes', action='store_true', help='bỏ qua bước hỏi xác nhận (bắt buộc khi không có terminal, ví dụ cron/CI)')
    p.add_argument('--dry-run', action='store_true', help='chỉ báo sẽ xóa/đặt lại những gì, không sửa dữ liệu')
    p.add_argument('--no-verify', action='store_true', help='không chụp ảnh trước/sau để so sánh (mặc định có)')
    p.add_argument('--report', metavar='FILE', help='ghi kết quả replay (JSON) ra FILE, dùng làm biên bản cho AC-08')
    p.add_argument('--json', action='store_true', help='in kết quả replay dạng JSON')
    return p


def validate_args(args):
    """Trả thông điệp lỗi (tiếng Việt) nếu tổ hợp tham số sai, ngược lại None."""
    if args.reset and args.from_block is None:
        return '--reset cần --from-block N (replay từ đầu: --from-block 0 --reset).'
    if args.from_block is not None and not args.reset:
        return '--from-block chỉ dùng cùng --reset (đây là thao tác xóa dữ liệu dẫn xuất, phải nói rõ).'
    if args.from_block is not None and args.from_block < 0:
        return '--from-block phải >= 0.'
    if args.reset and args.once:
        return '--once và --reset không dùng chung.'
    if (args.yes or args.dry_run or args.no_verify or args.report or args.json) and not args.reset:
        return 'Các tùy chọn --yes/--dry-run/--no-verify/--report/--json chỉ dùng cùng --from-block N --reset.'
    return None


def _confirm(args, stdin=sys.stdin, input_fn=input):
    """Hỏi xác nhận trước khi xóa. True nếu được phép tiếp tục."""
    if args.yes or args.dry_run:
        return True
    if not stdin.isatty():
        print('Replay sẽ XÓA dữ liệu dẫn xuất từ chuỗi. Không có terminal để xác nhận: thêm --yes nếu đúng ý.', file=sys.stderr)
        return False
    print(f'Replay từ block {args.from_block}: xóa chain_events và đặt lại trạng thái đơn Web3 rồi dựng lại từ chuỗi.')
    return input_fn('Gõ RESET để tiếp tục: ').strip() == 'RESET'


def format_report(result):
    """Chuỗi nhiều dòng cho người đọc."""
    r = result['reset'] or {}
    lines = []
    tag = 'DRY-RUN (không sửa gì)' if r.get('dry_run') else 'RESET'
    lines.append(f"[replay] {tag} từ block {r.get('from_block')}: {r.get('events_deleted')} sự kiện, "
                 f"{r.get('orders_with_events')} đơn theo sự kiện, {r.get('orders_swept')} đơn quét thêm, "
                 f"{r.get('pending_cleared')} dòng sổ chờ rút, con trỏ -> {r.get('cursor')}")
    for n in result.get('notes', []):
        lines.append(f'[replay] LƯU Ý: {n}')
    rp = result.get('replayed')
    if rp:
        lines.append(f"[replay] dựng lại: {rp['new_events']} sự kiện mới / {rp['events']} log, tới block {rp['last_block']}"
                     + (f" (dừng đúng tại block đã chụp {result['pinned_block']})" if result.get('pinned_block') is not None else ''))
    if result.get('verified') is True:
        lines.append('[replay] SO SÁNH TRƯỚC/SAU: KHỚP 100% (đơn, tồn kho, sổ chờ rút, thông báo, đề xuất phán quyết, chain_events)')
    elif result.get('verified') is False:
        lines.append('[replay] SO SÁNH TRƯỚC/SAU: KHÁC NHAU')
        lines.extend('  ' + d for d in result['differences'])
    elif not r.get('dry_run'):
        lines.append('[replay] không so sánh trước/sau (--no-verify hoặc chuỗi đã bị thay)')
    return '\n'.join(lines)


def run_replay(args, indexer, conn, chain, start_block, out=print):
    """Phần có logic của chế độ replay (tách khỏi main để test). Trả mã thoát."""
    from slopee_web3.adapters.indexer import replay as replay_mod
    if not indexer.acquire_lock(conn):
        print('Đã có Indexer khác đang chạy: tắt nó rồi chạy lại replay (./scripts/e2e_stack.sh down hoặc dừng tiến trình Indexer).',
              file=sys.stderr)
        return EXIT_ERROR
    try:
        result = replay_mod.replay(indexer, conn, chain, from_block=args.from_block, start_block=start_block,
                                   dry_run=args.dry_run, verify=not args.no_verify)
    finally:
        indexer.release_lock(conn)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    out(json.dumps(result, ensure_ascii=False, default=str) if args.json else format_report(result))
    return EXIT_OK if result['ok'] else EXIT_DIFFERENT


def main(argv=None):
    args = build_parser().parse_args(argv)
    problem = validate_args(args)
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(EXIT_ERROR)
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    load_dotenv(os.path.join(backend, '.env'))
    load_dotenv(os.path.join(backend, '.env.web3'))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    from slopee_web3.adapters.logging_filter import install
    install()
    from routes.auth import get_db_connection
    from slopee_web3.settings import Web3Settings
    from slopee_web3.adapters.web3_chain import Web3Chain
    from slopee_web3.adapters.indexer import Indexer, IndexerLockBusy
    s = Web3Settings.from_env()
    if s is None:
        sys.exit('Chưa cấu hình Web3: chạy scripts/bootstrap.sh để sinh backend/.env.web3')
    chain = Web3Chain(s.rpc_url, s.escrow_address, timeout=s.rpc_timeout)
    ix = Indexer(get_db_connection, chain, start_block=s.indexer_start_block, confirmations=s.confirmations,
                 reorg_depth=s.reorg_depth, poll_seconds=s.poll_seconds)
    if args.reset:
        if not _confirm(args):
            sys.exit(EXIT_ERROR)
        from slopee_web3.ports.chain_port import ChainUnavailable
        conn = get_db_connection()
        try:
            code = run_replay(args, ix, conn, chain, s.indexer_start_block)
        except ChainUnavailable as e:
            print(f'Không kết nối được RPC của chuỗi: {e}', file=sys.stderr)
            code = EXIT_ERROR
        except Exception as e:      # noqa: BLE001 - mất DB, lỗi handler...: phải ra mã 2 chứ không phải 1 (1 = "dựng lại nhưng KHÁC")
            logging.getLogger('slopee.indexer.replay').exception('Replay lỗi')
            print(f'Replay không chạy được ({type(e).__name__}): {e}. Dữ liệu dẫn xuất được giữ nguyên như trước bước lỗi '
                  '(mỗi bước là một giao dịch); chạy lại script để tiếp tục.', file=sys.stderr)
            code = EXIT_ERROR
        finally:
            conn.close()
        sys.exit(code)
    if args.once:
        conn = get_db_connection()
        try:
            if not ix.acquire_lock(conn):
                sys.exit('Đã có Indexer khác đang chạy.')
            print(ix.run_once(conn))
        finally:
            conn.close()
        return
    try:
        ix.run_forever()
    except IndexerLockBusy as e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
