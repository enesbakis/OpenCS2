import os
import types

import pytest

from app.security import (
    ROLES, has_role, is_safe_redirect_url, is_within_directory, safe_redirect_target,
)


@pytest.mark.parametrize('target, expected', [
    ('/', True),
    ('/maps/', True),
    ('/plugins/edit/Foo?file=a.json', True),
    ('https://evil.example', False),
    ('http://evil.example/', False),
    ('//evil.example', False),
    ('/\\evil.example', False),
    ('\\\\evil.example', False),
    ('javascript:alert(1)', False),
    ('/\t/evil.example', False),
    ('/\r\nSet-Cookie: x=1', False),
    ('maps/', False),
    ('', False),
    (None, False),
    (123, False),
])
def test_is_safe_redirect_url(target, expected):
    assert is_safe_redirect_url(target) is expected


def test_safe_redirect_target_falls_back():
    assert safe_redirect_target('//evil.example', '/') == '/'
    assert safe_redirect_target('/audit/', '/') == '/audit/'


def _user(role, authenticated=True):
    return types.SimpleNamespace(role=role, is_authenticated=authenticated)


def test_role_hierarchy():
    assert ROLES == ('viewer', 'operator', 'admin')
    assert has_role(_user('admin'), 'viewer')
    assert has_role(_user('admin'), 'admin')
    assert has_role(_user('operator'), 'operator')
    assert not has_role(_user('operator'), 'admin')
    assert has_role(_user('viewer'), 'viewer')
    assert not has_role(_user('viewer'), 'operator')


def test_unknown_role_and_anonymous_get_nothing():
    assert not has_role(_user('superuser'), 'viewer')
    assert not has_role(_user(None), 'viewer')
    assert not has_role(_user('admin', authenticated=False), 'viewer')


def test_has_role_rejects_typo_in_required_role():
    with pytest.raises(ValueError):
        has_role(_user('admin'), 'adm1n')


def test_is_within_directory(tmp_path):
    base = tmp_path / 'plugins' / 'Foo'
    sibling = tmp_path / 'plugins' / 'Foo2'
    base.mkdir(parents=True)
    sibling.mkdir()
    assert is_within_directory(str(base), str(base / 'config.json'))
    assert is_within_directory(str(base), str(base / 'sub' / 'x.cfg'))
    assert is_within_directory(str(base), str(base))
    # Shares the "Foo" prefix but is a different directory.
    assert not is_within_directory(str(base), str(sibling / 'secret.cfg'))
    assert not is_within_directory(str(base), os.path.join(str(base), '..', 'Foo2', 'x'))
    assert not is_within_directory(str(base), str(tmp_path))


def test_is_within_directory_follows_symlinks(tmp_path):
    base = tmp_path / 'plugin'
    outside = tmp_path / 'outside.txt'
    base.mkdir()
    outside.write_text('secret')
    link = base / 'link.cfg'
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks not supported here')
    assert not is_within_directory(str(base), str(link))
