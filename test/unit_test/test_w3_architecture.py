"""T-ARCH-01 (SDD 3.3): domain không I/O; application chỉ phụ thuộc domain + ports; ports chỉ phụ thuộc domain."""
import ast
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / 'backend' / 'slopee_web3'
STDLIB = set(sys.stdlib_module_names)
FORBIDDEN_IN_DOMAIN = {'flask', 'pymysql', 'web3', 'eth_account', 'eth_utils', 'requests', 'os', 'socket', 'time',
                       'datetime_now', 'subprocess', 'sqlite3', 'urllib', 'http', 'secrets', 'random'}


def _imports(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name.split('.')[0], 0, a.name
        elif isinstance(n, ast.ImportFrom):
            yield (n.module or '').split('.')[0], n.level, n.module or ''


def _files(layer):
    return sorted((PKG / layer).rglob('*.py'))


def _relative_target(path, level, module):
    """Với import tương đối, trả lớp đích (domain/ports/application/adapters) hoặc None."""
    parts = list(path.relative_to(PKG).parts[:-1])
    base = parts[:len(parts) - (level - 1)] if level else []
    target = (base + module.split('.')) if module else base
    return target[0] if target else None


@pytest.mark.parametrize('f', _files('domain'), ids=lambda p: p.name)
def test_domain_is_pure(f):
    for top, level, module in _imports(f):
        if level == 0:
            assert top in STDLIB or top == '', f'{f.name} import ngoài stdlib: {module}'
            assert top not in FORBIDDEN_IN_DOMAIN, f'{f.name} import mô-đun có I/O: {module}'
        else:
            assert _relative_target(f, level, module) in (None, 'domain'), f'{f.name} import ngược lớp: {module}'


@pytest.mark.parametrize('f', _files('ports'), ids=lambda p: p.name)
def test_ports_depend_only_on_domain(f):
    for top, level, module in _imports(f):
        if level == 0:
            assert top in STDLIB, f'{f.name} import ngoài stdlib: {module}'
        else:
            assert _relative_target(f, level, module) in (None, 'domain', 'ports'), f'{f.name} import ngược lớp: {module}'


@pytest.mark.parametrize('f', _files('application'), ids=lambda p: p.name)
def test_application_depends_only_on_domain_and_ports(f):
    for top, level, module in _imports(f):
        if level == 0:
            assert top in STDLIB, f'{f.name} import thư viện ngoài (phải qua port): {module}'
        else:
            assert _relative_target(f, level, module) in (None, 'domain', 'ports', 'application'), \
                f'{f.name} import adapter: {module}'
