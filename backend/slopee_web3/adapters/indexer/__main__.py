"""Chạy Indexer như một tiến trình riêng (khác tiến trình Flask). Cần backend/.env.web3 (bootstrap.sh sinh) và MySQL."""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv


def main(argv=None):
    p = argparse.ArgumentParser(description='Slopee Indexer')
    p.add_argument('--once', action='store_true', help='chạy một vòng rồi thoát (dùng cho test/gỡ lỗi)')
    args = p.parse_args(argv)
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
