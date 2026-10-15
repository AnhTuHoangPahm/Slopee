"""UC-01 trên MySQL THẬT (I-04, I-07 phần backend): tạo lô, ký báo giá, giữ tồn kho, cấp lại báo giá, đua song song."""
import json
import threading

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from flask import Flask

from auth_utils import issue_token
from slopee_web3.adapters.flask_api import container, register_web3
from slopee_web3.adapters.mysql_repos import MySqlUnitOfWork
from slopee_web3.domain import quote as q
from slopee_web3.domain.errors import DomainError
from w3_support import (ADDR, CHAIN_ID, ESCROW, KEYS, TOKEN, Env, cart_item, category, connect, shop_with_product,
                        user)

pytestmark = pytest.mark.mysql

SETTING_KEYS = ('FX_VND_PER_TOKEN', 'QUOTE_TTL_SECONDS', 'PLATFORM_FEE_BPS')


@pytest.fixture
def db(mysql_db):
    conn = connect()
    conn.autocommit(True)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_wallets")
    saved = {}
    cur.execute("SELECT setting_key, setting_value FROM platform_settings")
    saved = {r['setting_key']: r['setting_value'] for r in cur.fetchall()}
    yield cur
    for k, v in saved.items():                         # trả lại cấu hình sàn cho các test khác
        cur.execute("UPDATE platform_settings SET setting_value=%s WHERE setting_key=%s", (v, k))
    cur.execute("INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES (%s,%s)", ('FX_VND_PER_TOKEN', '25000'))
    for k in SETTING_KEYS:
        cur.execute("INSERT IGNORE INTO platform_settings (setting_key, setting_value) VALUES (%s,%s)", (k, saved.get(k, '1')))
    conn.close()


@pytest.fixture
def env():
    return Env()


def setting(db, key, value):
    db.execute("INSERT INTO platform_settings (setting_key, setting_value) VALUES (%s,%s) "
               "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (key, value))


def buyer_with_wallet(db):
    uid = user(db)
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (uid, ADDR['buyer'].lower()))
    return uid


def seller_shop(db, n=1, *, stock=10, price=100_000, category_id=None, link=True, name='Áo thun'):
    """Tạo seller + shop + 1 sản phẩm; ví merchant{n}. Trả (seller_id, shop_id, product_id)."""
    sid = user(db, 'seller')
    if link:
        db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (sid, ADDR[f'merchant{n}'].lower()))
    shop, pid = shop_with_product(db, sid, category_id=category_id, stock=stock, price=price, name=name)
    return sid, shop, pid


def code(fn, *a, **kw):
    with pytest.raises(DomainError) as e:
        fn(*a, **kw)
    return e.value


def one(db, sql, *a):
    db.execute(sql, a)
    return db.fetchone()


def count(db, sql, *a):
    db.execute(sql, a)
    return len(db.fetchall())


def stock(db, pid):
    return one(db, "SELECT inStock FROM products WHERE id=%s", pid)['inStock']


def recover_quote_signer(quote_msg, signature):
    full = {'types': {'EIP712Domain': [{'name': 'name', 'type': 'string'}, {'name': 'version', 'type': 'string'},
                                       {'name': 'chainId', 'type': 'uint256'}, {'name': 'verifyingContract', 'type': 'address'}],
                      'OrderQuote': json.loads(open('shared/eip712/types.json', encoding='utf-8').read())['types']['OrderQuote']},
            'primaryType': 'OrderQuote',
            'domain': {'name': 'SlopeeEscrow', 'version': '1', 'chainId': CHAIN_ID, 'verifyingContract': ESCROW},
            'message': {k: (v if k in ('buyer', 'merchant', 'token', 'docHash') else int(v)) for k, v in quote_msg.items()}}
    return Account.recover_message(encode_typed_data(full_message=full), signature=signature)


# ====================================================================== tạo đơn: đường chính
def test_single_shop_checkout_persists_everything_consistently(env, db):
    buyer = buyer_with_wallet(db)
    seller, shop, pid = seller_shop(db, 1, stock=10, price=100_000)
    item = cart_item(db, buyer, pid, 2)

    out = env.quote.create_checkout(buyer, [item])

    assert out['decimals'] == 6 and out['symbol'] == 'mUSD' and out['token_address'] == TOKEN
    assert out['deadline'] == 1_800_000_000 + 900 and out['server_time'] == 1_800_000_000
    assert len(out['orders']) == 1
    o = out['orders'][0]
    assert o['price_vnd'] == 200_000 and o['amount_raw'] == '8000000' and out['total_amount_raw'] == '8000000'
    assert o['fx'] == '25000.0000' and o['fee_bps'] == 300
    assert (o['inspection_duration'], o['dispute_timeout']) == (259_200, 2_592_000) and o['policy_code'] == 'GENERAL'
    m = o['quote']
    assert m['buyer'] == ADDR['buyer'] and m['merchant'] == ADDR['merchant1'] and m['token'] == TOKEN
    assert m['amount'] == '8000000' and m['orderId'] == o['onchain_order_id'] and m['deadline'] == str(out['deadline'])

    w = one(db, "SELECT * FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert w['status'] == 'PENDING_PAYMENT' and w['amount_raw'] == '8000000' and w['price_vnd'] == 200_000
    assert w['buyer_wallet'] == ADDR['buyer'].lower() and w['merchant_wallet'] == ADDR['merchant1'].lower()
    assert w['buyer_user_id'] == buyer and w['merchant_user_id'] == seller and w['shop_id'] == shop
    assert w['onchain_order_id'] == int(o['onchain_order_id']) and w['checkout_group_id'] == out['checkout_group_id']
    assert str(w['fx_vnd_per_token']) == '25000.0000' and w['doc_hash'] == m['docHash']

    legacy = one(db, "SELECT status, totalAmount, paymentMethodId FROM orders WHERE id=%s", o['order_id'])
    assert legacy['status'] == 'pending' and int(legacy['totalAmount']) == 200_000 and legacy['paymentMethodId'] is None
    line = one(db, "SELECT productId, quantity, unitPrice, snapshotProductName FROM orderLines WHERE orderId=%s", o['order_id'])
    assert (line['productId'], line['quantity'], int(line['unitPrice']), line['snapshotProductName']) == (pid, 2, 100_000, 'Áo thun')
    assert stock(db, pid) == 8                                              # giữ chỗ tồn kho
    g = one(db, "SELECT total_amount_raw, order_count, token_address FROM checkout_groups WHERE group_id=%s", out['checkout_group_id'])
    assert (g['total_amount_raw'], g['order_count'], g['token_address']) == ('8000000', 1, TOKEN.lower())
    qrow = one(db, "SELECT quote_json, signature, deadline FROM order_quotes WHERE order_id=%s", o['order_id'])
    assert qrow['signature'] == o['signature'] and qrow['deadline'] == out['deadline'] and json.loads(qrow['quote_json']) == m
    assert one(db, "SELECT COUNT(*) AS c FROM cartItems WHERE id=%s", item)['c'] == 1   # giỏ chỉ bị xóa khi Indexer thấy LOCKED


def test_quote_is_signed_by_quote_signer_and_dochash_is_reproducible_from_db(env, db):
    buyer = buyer_with_wallet(db)
    _, _, p1 = seller_shop(db, 1, price=150_000)
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, p1, 2)])
    o = out['orders'][0]
    assert recover_quote_signer(o['quote'], o['signature']) == ADDR['quote_signer']
    # băm lại tóm tắt từ chính dữ liệu trong DB phải ra đúng docHash đã ký (dùng làm bằng chứng khi tranh chấp)
    lines = [dict(product_id=r['productId'], quantity=r['quantity'], unit_price_vnd=int(r['unitPrice']))
             for r in _all(db, "SELECT productId, quantity, unitPrice FROM orderLines WHERE orderId=%s", o['order_id'])]
    created = one(db, "SELECT UNIX_TIMESTAMP(created_at) AS t FROM orders WHERE id=%s", o['order_id'])['t']
    summary = q.build_summary(o['order_id'], lines, 300_000, int(created))
    assert q.doc_hash(summary, keccak) == o['quote']['docHash']


def _all(db, sql, *a):
    db.execute(sql, a)
    return list(db.fetchall())


def test_multi_shop_batch_creates_one_order_per_shop_in_one_group(env, db):
    buyer = buyer_with_wallet(db)
    shops = [seller_shop(db, n, price=100_000 * n) for n in (1, 2, 3)]
    items = [cart_item(db, buyer, s[2], 1) for s in shops]
    out = env.quote.create_checkout(buyer, items)
    assert [o['shop_id'] for o in out['orders']] == [s[1] for s in shops]
    ids = [o['onchain_order_id'] for o in out['orders']]
    assert len(set(ids)) == 3 and all(int(i) < 2 ** 53 for i in ids)
    assert len({o['quote']['deadline'] for o in out['orders']}) == 1       # cùng hạn cho cả lô
    assert [o['amount_raw'] for o in out['orders']] == ['4000000', '8000000', '12000000']
    assert out['total_amount_raw'] == '24000000'
    assert [o['quote']['merchant'] for o in out['orders']] == [ADDR['merchant1'], ADDR['merchant2'], ADDR['merchant3']]
    assert count(db, "SELECT 1 FROM order_web3 WHERE checkout_group_id=%s", out['checkout_group_id']) == 3
    assert one(db, "SELECT order_count FROM checkout_groups WHERE group_id=%s", out['checkout_group_id'])['order_count'] == 3


def test_two_products_of_one_shop_become_one_order_with_summed_price(env, db):
    buyer = buyer_with_wallet(db)
    seller, shop, p1 = seller_shop(db, 1, price=50_000)
    db.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) "
               "SELECT 'second-prod-01', categoryId, shopId, 'B', 5, 70000, TRUE FROM products WHERE id=%s", (p1,))
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, p1, 2), cart_item(db, buyer, 'second-prod-01', 1)])
    assert len(out['orders']) == 1 and out['orders'][0]['price_vnd'] == 170_000
    assert count(db, "SELECT 1 FROM orderLines WHERE orderId=%s", out['orders'][0]['order_id']) == 2


def test_cart_item_ids_are_deduplicated(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1)
    item = cart_item(db, buyer, pid, 1)
    out = env.quote.create_checkout(buyer, [item, item, item])
    assert out['orders'][0]['price_vnd'] == 100_000 and stock(db, pid) == 9


def test_amount_rounds_up_and_group_total_is_sum_of_rounded_orders(env, db):
    buyer = buyer_with_wallet(db)
    setting(db, 'FX_VND_PER_TOKEN', '3')
    s1, s2 = seller_shop(db, 1, price=10), seller_shop(db, 2, price=10)
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, s1[2]), cart_item(db, buyer, s2[2])])
    assert [o['amount_raw'] for o in out['orders']] == ['3333334', '3333334'] and out['total_amount_raw'] == '6666668'


# ====================================================================== chính sách + phí + thời gian
def test_policy_is_max_of_each_duration_across_categories_of_one_shop(env, db):
    buyer = buyer_with_wallet(db)
    cat_a, cat_b = category(db), category(db)
    db.execute("INSERT INTO category_policy_map (category_id, policy_code) VALUES (%s,'PERISHABLE'),(%s,'CUSTOM_BULKY')", (cat_a, cat_b))
    seller, shop, p1 = seller_shop(db, 1, category_id=cat_a)
    db.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) VALUES ('pol-prod-b-0001',%s,%s,'B',5,1000,TRUE)", (cat_b, shop))
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, p1), cart_item(db, buyer, 'pol-prod-b-0001')])
    o = out['orders'][0]
    assert (o['inspection_duration'], o['dispute_timeout'], o['policy_code']) == (1_209_600, 5_184_000, 'CUSTOM_BULKY')
    w = one(db, "SELECT policy_code, inspection_duration, dispute_timeout FROM order_web3 WHERE order_id=%s", o['order_id'])
    assert (w['policy_code'], w['inspection_duration'], w['dispute_timeout']) == ('CUSTOM_BULKY', 1_209_600, 5_184_000)


def test_each_shop_gets_its_own_policy(env, db):
    buyer = buyer_with_wallet(db)
    cat = category(db)
    db.execute("INSERT INTO category_policy_map (category_id, policy_code) VALUES (%s,'ELECTRONICS')", (cat,))
    s1, s2 = seller_shop(db, 1, category_id=cat), seller_shop(db, 2)
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, s1[2]), cart_item(db, buyer, s2[2])])
    assert [o['policy_code'] for o in out['orders']] == ['ELECTRONICS', 'GENERAL']
    assert out['orders'][0]['inspection_duration'] == 604_800 and out['orders'][1]['inspection_duration'] == 259_200


@pytest.mark.parametrize('cfg,cap,expected', [(300, 300, 300), (300, 200, 200), (150, 300, 150), (0, 300, 0)])
def test_fee_never_exceeds_onchain_cap(db, cfg, cap, expected):
    env = Env(fee_cap=cap)
    buyer = buyer_with_wallet(db)
    setting(db, 'PLATFORM_FEE_BPS', str(cfg))
    _, _, pid = seller_shop(db, 1)
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, pid)])
    assert out['orders'][0]['fee_bps'] == expected and out['orders'][0]['quote']['feeBps'] == str(expected) and expected <= cap


def test_deadline_uses_chain_time_when_ahead_of_system_clock(db):
    env = Env(system_now=1_800_000_000, chain_ts=1_800_100_000)
    buyer = buyer_with_wallet(db)
    setting(db, 'QUOTE_TTL_SECONDS', '600')
    _, _, pid = seller_shop(db, 1)
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, pid)])
    assert out['deadline'] == 1_800_100_600 and out['server_time'] == 1_800_100_000


# ====================================================================== lỗi nghiệp vụ: không để lại dấu vết
def _nothing_persisted(db, buyer, pids, stocks):
    assert count(db, "SELECT 1 FROM orders WHERE userId=%s", buyer) == 0
    assert count(db, "SELECT 1 FROM checkout_groups WHERE buyer_user_id=%s", buyer) == 0
    for p, s in zip(pids, stocks):
        assert stock(db, p) == s


def test_buyer_without_wallet_is_rejected(env, db):
    buyer = user(db)
    _, _, pid = seller_shop(db, 1)
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, pid)])
    assert e.code == 'WALLET_NOT_LINKED' and e.extra['party'] == 'buyer'
    _nothing_persisted(db, buyer, [pid], [10])


def test_merchant_without_wallet_is_rejected_for_whole_batch(env, db):
    buyer = buyer_with_wallet(db)
    ok, bad = seller_shop(db, 1), seller_shop(db, 2, link=False)
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, ok[2]), cart_item(db, buyer, bad[2])])
    assert e.code == 'WALLET_NOT_LINKED' and e.extra['party'] == 'merchant' and e.extra['shop_id'] == bad[1]
    assert e.extra['shop_name'].startswith('Shop ') and e.extra['shop_name'] in e.message      # giao diện nêu đích danh shop
    _nothing_persisted(db, buyer, [ok[2], bad[2]], [10, 10])


def test_cannot_buy_from_own_shop(env, db):
    seller, shop, pid = seller_shop(db, 1)
    db.execute("DELETE FROM user_wallets WHERE user_id=%s", (seller,))
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (seller, ADDR['buyer'].lower()))
    e = code(env.quote.create_checkout, seller, [cart_item(db, seller, pid)])
    assert e.code == 'SELF_PURCHASE'


def test_more_than_five_shops_rejected_and_nothing_changes(env, db):
    buyer = buyer_with_wallet(db)
    shops = [seller_shop(db, n) for n in range(1, 7)]
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, s[2]) for s in shops])
    assert e.code == 'BATCH_TOO_LARGE' and e.extra == {'max': 5, 'shops': 6}
    _nothing_persisted(db, buyer, [s[2] for s in shops], [10] * 6)
    ok = env.quote.create_checkout(buyer, [cart_item(db, buyer, s[2]) for s in shops[:5]])   # đúng 5 shop thì được
    assert len(ok['orders']) == 5


def test_empty_and_foreign_cart_items(env, db):
    buyer, other = buyer_with_wallet(db), user(db)
    _, _, pid = seller_shop(db, 1)
    foreign = cart_item(db, other, pid)
    assert code(env.quote.create_checkout, buyer, []).code == 'EMPTY_CART'
    assert code(env.quote.create_checkout, buyer, [foreign]).code == 'CART_ITEM_NOT_FOUND'
    assert code(env.quote.create_checkout, buyer, ['does-not-exist']).code == 'CART_ITEM_NOT_FOUND'
    mine = cart_item(db, buyer, pid)
    assert code(env.quote.create_checkout, buyer, [mine, foreign]).code == 'CART_ITEM_NOT_FOUND'   # một dòng lạ -> từ chối cả lô
    _nothing_persisted(db, buyer, [pid], [10])


def test_out_of_stock_and_inactive_product(env, db):
    buyer = buyer_with_wallet(db)
    _, _, scarce = seller_shop(db, 1, stock=1)
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, scarce, 2)])
    assert e.code == 'OUT_OF_STOCK' and e.extra['product_id'] == scarce
    _, _, off = seller_shop(db, 2)
    db.execute("UPDATE products SET isActive=FALSE WHERE id=%s", (off,))
    assert code(env.quote.create_checkout, buyer, [cart_item(db, buyer, off)]).code == 'PRODUCT_UNAVAILABLE'
    _nothing_persisted(db, buyer, [scarce, off], [1, 10])


def test_same_product_in_two_cart_lines_is_checked_against_total_quantity(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1, stock=3)
    items = [cart_item(db, buyer, pid, 2), cart_item(db, buyer, pid, 2)]        # 2 + 2 > 3
    assert code(env.quote.create_checkout, buyer, items).code == 'OUT_OF_STOCK'
    assert stock(db, pid) == 3


@pytest.mark.parametrize('key,value', [('FX_VND_PER_TOKEN', '0'), ('FX_VND_PER_TOKEN', 'abc'), ('FX_VND_PER_TOKEN', '-1'),
                                       ('QUOTE_TTL_SECONDS', '10'), ('QUOTE_TTL_SECONDS', 'x'), ('PLATFORM_FEE_BPS', '1001'),
                                       ('PLATFORM_FEE_BPS', '-1')])
def test_invalid_platform_settings_are_reported_not_used(env, db, key, value):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1)
    setting(db, key, value)
    assert code(env.quote.create_checkout, buyer, [cart_item(db, buyer, pid)]).code == 'SETTING_INVALID'
    _nothing_persisted(db, buyer, [pid], [10])


def test_missing_setting_key_is_reported(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1)
    db.execute("DELETE FROM platform_settings WHERE setting_key='QUOTE_TTL_SECONDS'")
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, pid)])
    assert e.code == 'SETTING_INVALID' and 'QUOTE_TTL_SECONDS' in e.message


def test_zero_price_order_is_rejected_because_contract_rejects_zero_amount(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1, price=0)
    assert code(env.quote.create_checkout, buyer, [cart_item(db, buyer, pid)]).code == 'INVALID_AMOUNT'
    _nothing_persisted(db, buyer, [pid], [10])


def test_chain_down_fails_fast_and_changes_nothing(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1)
    item = cart_item(db, buyer, pid)
    env.chain.available = False
    assert code(env.quote.create_checkout, buyer, [item]).code == 'CHAIN_UNAVAILABLE'
    _nothing_persisted(db, buyer, [pid], [10])
    env.chain.available = True
    assert env.quote.create_checkout(buyer, [item])['orders']


def test_failure_on_second_shop_rolls_back_the_whole_batch(env, db):
    buyer = buyer_with_wallet(db)
    s1, s2 = seller_shop(db, 1), seller_shop(db, 2)
    items = [cart_item(db, buyer, s1[2]), cart_item(db, buyer, s2[2])]
    real, calls = env.signer.sign_quote, []

    def flaky(quote):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('HSM timeout')
        return real(quote)
    env.signer.sign_quote = flaky
    with pytest.raises(RuntimeError):
        env.quote.create_checkout(buyer, items)
    _nothing_persisted(db, buyer, [s1[2], s2[2]], [10, 10])
    env.signer.sign_quote = real
    assert len(env.quote.create_checkout(buyer, items)['orders']) == 2


def test_failure_after_stock_reservation_rolls_back_stock(env, db):
    buyer = buyer_with_wallet(db)
    s1, s2 = seller_shop(db, 1, stock=5), seller_shop(db, 2, stock=5)
    items = [cart_item(db, buyer, s1[2], 2), cart_item(db, buyer, s2[2], 2)]

    class ExplodingOnSecondOrder(MySqlUnitOfWork):
        def __enter__(self):
            super().__enter__()
            inner, calls = self.checkout.insert_order_web3, []

            def boom(row):
                calls.append(1)
                if len(calls) == 2:
                    raise RuntimeError('disk full')
                inner(row)
            self.checkout.insert_order_web3 = boom
            return self

    good = env.quote._uow
    env.quote._uow = lambda: ExplodingOnSecondOrder(connect)
    with pytest.raises(RuntimeError):
        env.quote.create_checkout(buyer, items)
    env.quote._uow = good
    _nothing_persisted(db, buyer, [s1[2], s2[2]], [5, 5])          # kể cả shop 1 đã trừ kho trước khi lỗi
    assert len(env.quote.create_checkout(buyer, items)['orders']) == 2


def test_second_checkout_for_same_products_is_refused_while_first_is_pending(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1)
    first = env.quote.create_checkout(buyer, [cart_item(db, buyer, pid, 1)])
    e = code(env.quote.create_checkout, buyer, [cart_item(db, buyer, pid, 1)])
    assert e.code == 'PENDING_GROUP_EXISTS' and e.extra['checkout_group_id'] == first['checkout_group_id']
    assert stock(db, pid) == 9                                        # không giữ chỗ hai lần


def test_onchain_ids_are_unique_across_orders_and_never_reused_after_rollback(env, db):
    buyer = buyer_with_wallet(db)
    ids = set()
    for n in (1, 2, 3):
        _, _, pid = seller_shop(db, n)
        out = env.quote.create_checkout(buyer, [cart_item(db, buyer, pid)])
        ids.add(out['orders'][0]['onchain_order_id'])
        db.execute("UPDATE order_web3 SET status='EXPIRED' WHERE checkout_group_id=%s", (out['checkout_group_id'],))
    assert len(ids) == 3


# ====================================================================== đua song song
def test_two_buyers_racing_for_the_last_unit_exactly_one_wins(db):
    env = Env()
    seller, shop, pid = seller_shop(db, 1, stock=1)
    buyers = []
    for n in (1, 2):
        u = user(db)
        db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (u, ADDR['buyer'].lower() if n == 1 else ADDR['stranger'].lower()))
        buyers.append((u, cart_item(db, u, pid, 1)))
    results, barrier = [], threading.Barrier(2)

    def go(u, item):
        barrier.wait()
        try:
            env.quote.create_checkout(u, [item])
            results.append('ok')
        except DomainError as e:
            results.append(e.code)
    ts = [threading.Thread(target=go, args=b) for b in buyers]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(results) == ['OUT_OF_STOCK', 'ok'], results
    assert stock(db, pid) == 0 and count(db, "SELECT 1 FROM order_web3 WHERE shop_id=%s", shop) == 1


def test_double_submit_of_same_cart_creates_a_single_group(db):
    env = Env()
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1, stock=10)
    item = cart_item(db, buyer, pid, 1)
    results, barrier = [], threading.Barrier(3)

    def go():
        barrier.wait()
        try:
            env.quote.create_checkout(buyer, [item])
            results.append('ok')
        except DomainError as e:
            results.append(e.code)
    ts = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count('ok') == 1 and results.count('PENDING_GROUP_EXISTS') == 2, results
    assert stock(db, pid) == 9 and count(db, "SELECT 1 FROM checkout_groups WHERE buyer_user_id=%s", buyer) == 1


def test_parallel_checkouts_of_different_buyers_get_distinct_onchain_ids(db):
    env = Env()
    buyer_keys = ['buyer', 'stranger', 'merchant5', 'merchant6']      # bốn ví người mua khác nhau
    work = []
    for n, key in enumerate(buyer_keys):
        u = user(db)
        db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (u, ADDR[key].lower()))
        _, _, pid = seller_shop(db, n + 1)                             # mỗi người mua một shop riêng (merchant1..4)
        work.append((u, cart_item(db, u, pid)))
    out_ids, errs, barrier = [], [], threading.Barrier(len(work))

    def go(u, item):
        barrier.wait()
        try:
            out_ids.append(env.quote.create_checkout(u, [item])['orders'][0]['onchain_order_id'])
        except Exception as e:     # noqa: BLE001
            errs.append(repr(e))
    ts = [threading.Thread(target=go, args=w) for w in work]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs
    assert len(set(out_ids)) == 4


# ====================================================================== cấp lại báo giá
def _group(env, db, shops=(1,), qty=1):
    buyer = buyer_with_wallet(db)
    ss = [seller_shop(db, n) for n in shops]
    out = env.quote.create_checkout(buyer, [cart_item(db, buyer, s[2], qty) for s in ss])
    return buyer, ss, out


def test_requote_keeps_ids_and_dochash_but_refreshes_deadline_fee_and_amount(db):
    env = Env()
    buyer, ss, first = _group(env, db, (1, 2))
    env.chain.block_ts = 1_800_000_500
    env.clock.system = 1_800_000_500
    env.chain.fee_cap = 100                                          # trần phí on-chain giảm
    setting(db, 'FX_VND_PER_TOKEN', '20000')
    second = env.quote.reissue_group_quotes(buyer, first['checkout_group_id'])

    assert [o['onchain_order_id'] for o in second['orders']] == [o['onchain_order_id'] for o in first['orders']]
    assert [o['order_id'] for o in second['orders']] == [o['order_id'] for o in first['orders']]
    assert [o['quote']['docHash'] for o in second['orders']] == [o['quote']['docHash'] for o in first['orders']]
    assert second['deadline'] == 1_800_000_500 + 900 > first['deadline']
    assert all(o['fee_bps'] == 100 for o in second['orders'])        # FEE_CAP_CHANGED: phí mới theo trần mới
    assert [o['amount_raw'] for o in second['orders']] == ['5000000', '5000000']          # 100000 / 20000 = 5 mUSD
    assert second['total_amount_raw'] == '10000000'
    for o in second['orders']:
        assert recover_quote_signer(o['quote'], o['signature']) == ADDR['quote_signer']
        assert one(db, "SELECT COUNT(*) AS c FROM order_quotes WHERE order_id=%s", o['order_id'])['c'] == 2   # giữ lịch sử
        w = one(db, "SELECT fee_bps, amount_raw, status FROM order_web3 WHERE order_id=%s", o['order_id'])
        assert (w['fee_bps'], w['amount_raw'], w['status']) == (100, '5000000', 'PENDING_PAYMENT')
    assert one(db, "SELECT total_amount_raw FROM checkout_groups WHERE group_id=%s", first['checkout_group_id'])['total_amount_raw'] == '10000000'
    assert stock(db, ss[0][2]) == 9                                  # không giữ chỗ thêm


def test_requote_of_someone_elses_group_is_not_found(env, db):
    buyer, _, out = _group(env, db)
    stranger = user(db)
    assert code(env.quote.reissue_group_quotes, stranger, out['checkout_group_id']).code == 'GROUP_NOT_FOUND'
    assert code(env.quote.reissue_group_quotes, buyer, 'no-such-group').code == 'GROUP_NOT_FOUND'
    assert code(env.quote.get_group, stranger, out['checkout_group_id']).code == 'GROUP_NOT_FOUND'


def test_requote_refused_when_an_order_already_exists_on_chain(env, db):
    buyer, _, out = _group(env, db, (1, 2))
    env.chain.states[int(out['orders'][1]['onchain_order_id'])] = 'LOCKED'     # đã nạp nhưng Indexer chưa kịp ghi
    e = code(env.quote.reissue_group_quotes, buyer, out['checkout_group_id'])
    assert e.code == 'INVALID_STATE'
    assert count(db, "SELECT 1 FROM order_quotes WHERE order_id IN (%s,%s)", out['orders'][0]['order_id'], out['orders'][1]['order_id']) == 2


def test_requote_refused_when_group_is_no_longer_pending(env, db):
    buyer, _, out = _group(env, db)
    db.execute("UPDATE order_web3 SET status='LOCKED' WHERE checkout_group_id=%s", (out['checkout_group_id'],))
    assert code(env.quote.reissue_group_quotes, buyer, out['checkout_group_id']).code == 'INVALID_STATE'


def test_requote_chain_down(env, db):
    buyer, _, out = _group(env, db)
    env.chain.available = False
    assert code(env.quote.reissue_group_quotes, buyer, out['checkout_group_id']).code == 'CHAIN_UNAVAILABLE'


def test_requote_uses_the_new_wallet_after_buyer_changed_wallet(env, db):
    buyer, _, out = _group(env, db)
    db.execute("UPDATE user_wallets SET is_active=0 WHERE user_id=%s", (buyer,))
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) VALUES (%s,%s,1)", (buyer, ADDR['stranger'].lower()))
    second = env.quote.reissue_group_quotes(buyer, out['checkout_group_id'])
    assert second['orders'][0]['quote']['buyer'] == ADDR['stranger']
    assert one(db, "SELECT buyer_wallet FROM order_web3 WHERE order_id=%s", out['orders'][0]['order_id'])['buyer_wallet'] == ADDR['stranger'].lower()


def test_requote_after_expiry_reserves_stock_again_and_reactivates(env, db):
    buyer, ss, out = _group(env, db, (1, 2), qty=2)
    # mô phỏng bộ quét hết hạn (Tuần 5): EXPIRED + orders cancelled + trả tồn kho
    db.execute("UPDATE order_web3 SET status='EXPIRED' WHERE checkout_group_id=%s", (out['checkout_group_id'],))
    for o in out['orders']:
        db.execute("UPDATE orders SET status='cancelled' WHERE id=%s", (o['order_id'],))
    for s in ss:
        db.execute("UPDATE products SET inStock = inStock + 2 WHERE id=%s", (s[2],))
    assert [stock(db, s[2]) for s in ss] == [10, 10]
    second = env.quote.reissue_group_quotes(buyer, out['checkout_group_id'])
    assert [stock(db, s[2]) for s in ss] == [8, 8]
    assert all(one(db, "SELECT status FROM order_web3 WHERE order_id=%s", o['order_id'])['status'] == 'PENDING_PAYMENT' for o in second['orders'])
    assert all(one(db, "SELECT status FROM orders WHERE id=%s", o['order_id'])['status'] == 'pending' for o in second['orders'])


def test_requote_after_expiry_fails_atomically_if_stock_is_gone(env, db):
    buyer, ss, out = _group(env, db, (1, 2), qty=2)
    db.execute("UPDATE order_web3 SET status='EXPIRED' WHERE checkout_group_id=%s", (out['checkout_group_id'],))
    db.execute("UPDATE products SET inStock = 10 WHERE id=%s", (ss[0][2],))
    db.execute("UPDATE products SET inStock = 1 WHERE id=%s", (ss[1][2],))              # shop 2 hết hàng
    assert code(env.quote.reissue_group_quotes, buyer, out['checkout_group_id']).code == 'OUT_OF_STOCK'
    assert stock(db, ss[0][2]) == 10 and stock(db, ss[1][2]) == 1                        # shop 1 không bị trừ dở
    assert {r['status'] for r in _all(db, "SELECT status FROM order_web3 WHERE checkout_group_id=%s", out['checkout_group_id'])} == {'EXPIRED'}


# ====================================================================== đọc lô + HTTP
def test_get_group_reports_orders_status_and_latest_deadline(env, db):
    buyer, _, out = _group(env, db, (1, 2))
    env.chain.block_ts = env.clock.system = 1_800_000_100
    env.quote.reissue_group_quotes(buyer, out['checkout_group_id'])
    g = env.quote.get_group(buyer, out['checkout_group_id'])
    assert g['status'] == 'PENDING_PAYMENT' and g['deadline'] == 1_800_000_100 + 900 and g['server_time'] == 1_800_000_100
    assert g['total_amount_raw'] == out['total_amount_raw'] and len(g['orders']) == 2
    assert all(o['status'] == 'PENDING_PAYMENT' and o['quote_deadline'] == g['deadline'] and o['deposit_tx_hash'] is None for o in g['orders'])
    db.execute("UPDATE order_web3 SET status='LOCKED' WHERE order_id=%s", (out['orders'][0]['order_id'],))
    assert env.quote.get_group(buyer, out['checkout_group_id'])['status'] == 'MIXED'


class _C:
    def __init__(self, env): self.env = env
    def wallet_service(self): return self.env.wallet
    def quote_service(self): return self.env.quote


def test_http_checkout_then_requote_then_read(env, db):
    container.set_container(_C(env))
    try:
        app = Flask(__name__)
        register_web3(app)
        c = app.test_client()
        buyer = buyer_with_wallet(db)
        _, _, pid = seller_shop(db, 1)
        item = cart_item(db, buyer, pid, 1)
        h = {'Authorization': f"Bearer {issue_token(buyer, 'user')}"}
        r = c.post('/api/orders', json={'cart_item_ids': [item]}, headers=h)
        assert r.status_code == 201
        gid = r.get_json()['checkout_group_id']
        assert c.get(f'/api/checkout-groups/{gid}', headers=h).get_json()['status'] == 'PENDING_PAYMENT'
        assert c.post(f'/api/checkout-groups/{gid}/quote', headers=h).status_code == 200
        dup = c.post('/api/orders', json={'cart_item_ids': [item]}, headers=h)
        assert dup.status_code == 409 and dup.get_json()['code'] == 'PENDING_GROUP_EXISTS'
        intruder = {'Authorization': f"Bearer {issue_token(user(db), 'user')}"}
        assert c.get(f'/api/checkout-groups/{gid}', headers=intruder).status_code == 404
        nw = user(db)
        no_wallet = {'Authorization': f"Bearer {issue_token(nw, 'user')}"}
        miss = c.post('/api/orders', json={'cart_item_ids': [cart_item(db, nw, pid)]}, headers=no_wallet)
        assert miss.status_code == 409 and miss.get_json()['code'] == 'WALLET_NOT_LINKED'
    finally:
        container.set_container(None)


# ====================================================================== điều kiện hiển thị lựa chọn Web3 (BR-07)
def test_eligibility_reports_each_shop_and_whether_all_are_linked(env, db):
    buyer = buyer_with_wallet(db)
    ok, bad = seller_shop(db, 1), seller_shop(db, 2, link=False)
    items = [cart_item(db, buyer, ok[2]), cart_item(db, buyer, bad[2])]
    out = env.quote.check_web3_eligibility(buyer, items)
    assert out['all_linked'] is False
    assert [(s['shop_id'], s['wallet_linked']) for s in out['shops']] == [(ok[1], True), (bad[1], False)]
    assert all(s['shop_name'].startswith('Shop ') for s in out['shops'])
    assert all(set(s) == {'shop_id', 'shop_name', 'wallet_linked'} for s in out['shops'])    # không lộ địa chỉ ví
    only_ok = env.quote.check_web3_eligibility(buyer, items[:1])
    assert only_ok['all_linked'] is True and len(only_ok['shops']) == 1


def test_eligibility_merges_products_of_one_shop_and_ignores_the_buyers_own_wallet(env, db):
    buyer = user(db)                                                   # người mua CHƯA liên kết ví: không ảnh hưởng kết quả này
    seller, shop, p1 = seller_shop(db, 1)
    db.execute("INSERT INTO products (id, categoryId, shopId, name, inStock, unitPrice, isActive) "
               "SELECT 'elig-prod-0001', categoryId, shopId, 'B', 5, 70000, TRUE FROM products WHERE id=%s", (p1,))
    out = env.quote.check_web3_eligibility(buyer, [cart_item(db, buyer, p1), cart_item(db, buyer, 'elig-prod-0001')])
    assert out == {'all_linked': True, 'shops': [{'shop_id': shop, 'shop_name': out['shops'][0]['shop_name'], 'wallet_linked': True}]}


def test_eligibility_is_a_pure_read_no_locks_no_writes(env, db):
    buyer = buyer_with_wallet(db)
    _, _, pid = seller_shop(db, 1, stock=7)
    item = cart_item(db, buyer, pid, 3)
    other = connect()
    try:                                                               # giữ khóa ghi trên sản phẩm: eligibility vẫn phải trả về ngay
        other.begin()
        other.cursor().execute("SELECT id FROM products WHERE id=%s FOR UPDATE", (pid,))
        other.cursor().execute("SELECT id FROM cartItems WHERE id=%s FOR UPDATE", (item,))
        assert env.quote.check_web3_eligibility(buyer, [item])['all_linked'] is True
    finally:
        other.rollback(); other.close()
    assert stock(db, pid) == 7 and count(db, "SELECT 1 FROM orders WHERE userId=%s", buyer) == 0
    assert count(db, "SELECT 1 FROM checkout_groups WHERE buyer_user_id=%s", buyer) == 0


def test_eligibility_rejects_empty_and_foreign_cart_items(env, db):
    buyer, other = buyer_with_wallet(db), user(db)
    _, _, pid = seller_shop(db, 1)
    foreign = cart_item(db, other, pid)
    assert code(env.quote.check_web3_eligibility, buyer, []).code == 'EMPTY_CART'
    assert code(env.quote.check_web3_eligibility, buyer, [foreign]).code == 'CART_ITEM_NOT_FOUND'     # không dò được giỏ người khác


def test_eligibility_agrees_with_checkout_decision(env, db):
    """Điều kiện hiển thị và quyết định thật phải cùng kết luận về ví người bán."""
    buyer = buyer_with_wallet(db)
    bad = seller_shop(db, 1, link=False)
    item = cart_item(db, buyer, bad[2])
    assert env.quote.check_web3_eligibility(buyer, [item])['all_linked'] is False
    assert code(env.quote.create_checkout, buyer, [item]).extra['shop_id'] == bad[1]
    db.execute("INSERT INTO user_wallets (user_id, address, is_active) SELECT sellerId, %s, 1 FROM shops WHERE id=%s", (ADDR['merchant1'].lower(), bad[1]))
    assert env.quote.check_web3_eligibility(buyer, [item])['all_linked'] is True
    assert env.quote.create_checkout(buyer, [item])['orders']


def test_http_eligibility(env, db):
    container.set_container(_C(env))
    try:
        app = Flask(__name__)
        register_web3(app)
        c = app.test_client()
        buyer = buyer_with_wallet(db)
        bad = seller_shop(db, 1, link=False)
        item = cart_item(db, buyer, bad[2])
        h = {'Authorization': f"Bearer {issue_token(buyer, 'user')}"}
        r = c.post('/api/orders/eligibility', json={'cart_item_ids': [item]}, headers=h)
        assert r.status_code == 200 and r.get_json()['all_linked'] is False and r.get_json()['shops'][0]['shop_id'] == bad[1]
        assert c.post('/api/orders/eligibility', json={'cart_item_ids': [item]}).status_code == 401
        miss = c.post('/api/orders', json={'cart_item_ids': [item]}, headers=h)
        assert miss.status_code == 409 and miss.get_json()['party'] == 'merchant' and miss.get_json()['shop_name'] == r.get_json()['shops'][0]['shop_name']
    finally:
        container.set_container(None)
