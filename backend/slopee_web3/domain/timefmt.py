"""Định dạng giờ hiển thị cho người dùng Việt Nam (UTC+7). Thuần: nhận giây UTC, không đọc đồng hồ."""
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def fmt_vn(ts):
    return datetime.fromtimestamp(int(ts), VN_TZ).strftime('%d/%m/%Y %H:%M')
