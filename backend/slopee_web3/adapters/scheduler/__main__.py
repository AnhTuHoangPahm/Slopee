"""Chạy Scheduler như một tiến trình riêng. Cần backend/.env.web3 (bootstrap.sh sinh) và MySQL."""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv


def main(argv=None):
    p = argparse.ArgumentParser(description='Slopee Scheduler (tác vụ nền)')
    p.add_argument('--once', action='store_true', help='chạy MỘT lần mọi tác vụ rồi thoát (test/gỡ lỗi)')
    args = p.parse_args(argv)
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    load_dotenv(os.path.join(backend, '.env'))
    load_dotenv(os.path.join(backend, '.env.web3'))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    from slopee_web3.adapters.logging_filter import install
    install()
    from routes.auth import get_db_connection
    from slopee_web3.adapters.flask_api import container as c
    from slopee_web3.adapters.scheduler import Scheduler, SchedulerLockBusy
    from slopee_web3.domain.errors import DomainError
    try:
        ct = c.get_container(get_db_connection)         # dựng + kiểm khóa vai trò khớp contract (SDD 5.6)
    except DomainError as e:
        sys.exit(e.message)
    sch = Scheduler(ct.jobs())
    if args.once:
        print(sch.run_due(force=True))
        return
    conn = get_db_connection()
    try:
        if not sch.acquire_lock(conn):
            raise SchedulerLockBusy('Đã có Scheduler khác đang chạy.')
        sch.run_forever()
    except SchedulerLockBusy as e:
        sys.exit(str(e))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
