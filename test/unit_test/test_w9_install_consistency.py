"""Tuần 9 [C]: các mặc định kết nối CSDL phải thống nhất, nếu không người làm theo INSTALL.md (chỉ đặt DB_PASSWORD) sẽ gặp
"Access denied for user 'slopee'" ở đăng ký/đăng nhập trong khi init_db/migrate vẫn chạy. Lỗi này từng có ở routes/auth.py
(mặc định 'slopee', mọi nơi khác 'root'); CI không thấy vì luôn đặt DB_USER=root."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"os\.environ\.get\(\s*['\"]DB_USER['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)")


def _defaults():
    found = {}
    for base in ('backend', 'scripts'):
        for p in (ROOT / base).rglob('*.py'):
            for m in PATTERN.finditer(p.read_text(encoding='utf-8')):
                found.setdefault(m.group(1), []).append(str(p.relative_to(ROOT)))
    return found


def test_db_user_default_is_root_everywhere():
    found = _defaults()
    assert found, 'không tìm thấy nơi nào đọc DB_USER: mẫu regex lỗi thời?'
    assert set(found) == {'root'}, f'mặc định DB_USER không thống nhất: {found}'


def test_every_route_module_that_opens_the_db_reads_db_user():
    """Mỗi module route có tự mở kết nối (pymysql.connect) đều phải đọc DB_USER, không được ghi cứng người dùng."""
    for p in (ROOT / 'backend' / 'routes').glob('*.py'):
        text = p.read_text(encoding='utf-8')
        if 'pymysql.connect(' in text:
            assert 'DB_USER' in text, f'{p.name}: pymysql.connect không đọc DB_USER'


def test_env_example_matches_code_default():
    text = (ROOT / 'backend' / '.env.example').read_text(encoding='utf-8')
    assert re.search(r'^DB_USER=root\s*$', text, re.M)
