import json
from decimal import Decimal

import pytest

from money import InvalidMoney, format_vnd, to_vnd


@pytest.mark.parametrize("value,expected", [
    (0, 0), (1500000, 1500000), ("25000", 25000), (Decimal("100000"), 100000),
    (Decimal("100000.00"), 100000), (10.0, 10),
])
def test_to_vnd_valid(value, expected):
    result = to_vnd(value)
    assert result == expected and isinstance(result, int)


@pytest.mark.parametrize("value", [-1, 10.5, "1e3x", "abc", None, True, float("nan"), Decimal("0.01"), 10 ** 15])
def test_to_vnd_invalid(value):
    with pytest.raises(InvalidMoney):
        to_vnd(value)


def test_format_vnd():
    assert format_vnd(1234567) == "1.234.567 ₫"
    assert format_vnd(0) == "0 ₫"


def test_no_float_rounding_drift():
    # 0.1 + 0.2 kiểu cộng float không xảy ra khi dùng int VND
    assert sum(to_vnd(x) * 3 for x in ["33333", "33333", "33334"]) == 300000


def test_json_provider_emits_numbers():
    from flask import Flask, jsonify
    from json_provider import SlopeeJSONProvider
    app = Flask(__name__)
    app.json = SlopeeJSONProvider(app)
    with app.app_context():
        body = json.loads(jsonify({"a": Decimal("150000"), "b": Decimal("4.5")}).get_data())
    assert body == {"a": 150000, "b": 4.5} and isinstance(body["a"], int)


def test_schema_money_columns_are_decimal_15_0():
    import os, re
    sql = open(os.path.join(os.path.dirname(__file__), '../../backend/schema.sql')).read()
    for col in ("balance", "unitPrice", "totalAmount"):
        assert re.search(rf"{col}\s+decimal\(15,\s*0\)", sql, re.I), col
    assert not re.search(r"decimal\(11", sql, re.I)
