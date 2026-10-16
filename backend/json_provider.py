"""JSON provider: Decimal -> số (int nếu nguyên) thay vì chuỗi, để frontend nhận number cho VND."""
from decimal import Decimal

from flask.json.provider import DefaultJSONProvider


class SlopeeJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return DefaultJSONProvider.default(o)
