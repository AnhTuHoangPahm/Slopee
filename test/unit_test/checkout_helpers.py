"""Dữ liệu giả dùng chung cho test thanh toán (không phải file test)."""

USER = 'fake-user-id'


def setup_checkout(cur, items, balance=1000000, pm_type='bank', pm_id=1, seller_bank='seller-bank'):
    """Dựng dữ liệu giả cho luồng thanh toán (P0-05: truy vấn tách riêng cartItems / products / shops / paymentMethods)."""
    cart_rows = [{"cartItemId": i["cartItemId"], "quantity": i["quantity"], "cartId": 1,
                  "selectedVariants": "{}", "productId": i["productId"]} for i in items]
    products = {}
    for i in items:
        products[i["productId"]] = {"productId": i["productId"], "unitPrice": i["unitPrice"],
                                    "inStock": i["inStock"], "shopId": i.get("shopId", 1), "name": i.get("name", "N")}
    shops = {p["shopId"]: {"shopId": p["shopId"], "shopName": "Shop A", "sellerId": "seller-1"} for p in products.values()}
    cur.on("FROM credentials", [{"passPhraseHash": "h"}])
    cur.on("FROM cartItems ci", cart_rows)
    cur.on("FROM products", list(products.values()))
    cur.on("FROM shops", list(shops.values()))
    cur.on("SELECT id FROM paymentMethods WHERE userId", [{"id": seller_bank}] if seller_bank else [])
    rows = [{"id": pm_id, "userId": USER, "methodType": pm_type, "balance": balance}]
    if seller_bank:
        rows.append({"id": seller_bank, "userId": "seller-1", "methodType": "bank", "balance": 0})
    cur.on("FROM paymentMethods WHERE id IN", rows)
    return cur


ITEMS = [
    {"cartItemId": 10, "quantity": 2, "productId": 100, "unitPrice": 100000, "inStock": 5, "name": "Item 1"},
    {"cartItemId": 11, "quantity": 1, "productId": 101, "unitPrice": 250000, "inStock": 2, "name": "Item 2"},
]
BODY = {"paymentMethodId": 1, "passPhrase": "123456", "cartItemIds": [10, 11]}
