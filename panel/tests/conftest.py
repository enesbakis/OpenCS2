import re

import pytest

from app import create_app
from app.models import create_user

ADMIN_USER = 'admin'
ADMIN_PASS = 'admin-pass-123'
PASSWORD = 'secret-pass-123'


def make_app(tmp_path, **overrides):
    data = tmp_path / 'cs2'
    data.mkdir(exist_ok=True)
    config = {
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-0123456789abcdef',
        'DATABASE': str(tmp_path / 'panel.db'),
        'CS2_DATA_PATH': str(data),
        'WTF_CSRF_ENABLED': False,
        # Unroutable RCON target: any accidental RCON call fails fast.
        'RCON_HOST': '127.0.0.1',
        'RCON_PORT': 1,
        'RCON_PASSWORD': 'test',
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('PANEL_ADMIN_USER', ADMIN_USER)
    monkeypatch.setenv('PANEL_ADMIN_PASS', ADMIN_PASS)
    return make_app(tmp_path)


@pytest.fixture
def csrf_app(tmp_path, monkeypatch):
    monkeypatch.setenv('PANEL_ADMIN_USER', ADMIN_USER)
    monkeypatch.setenv('PANEL_ADMIN_PASS', ADMIN_PASS)
    return make_app(tmp_path, WTF_CSRF_ENABLED=True)


@pytest.fixture
def make_user(app):
    def _make(username, role):
        create_user(app.config['DATABASE'], username, PASSWORD, role)
        return username
    return _make


def login(client, username, password=PASSWORD, next_url=None):
    url = '/login' if next_url is None else f'/login?next={next_url}'
    return client.post(url, data={'username': username, 'password': password})


@pytest.fixture
def login_as(app, make_user):
    """Return a fresh test client logged in with the given role."""
    def _login(role):
        if role == 'admin':
            username, password = ADMIN_USER, ADMIN_PASS
        else:
            username, password = make_user(f'user_{role}', role), PASSWORD
        client = app.test_client()
        resp = login(client, username, password)
        assert resp.status_code == 302, resp.data
        return client
    return _login


@pytest.fixture
def rcon_calls(monkeypatch):
    """Replace RCON in every module with a recorder; returns the call list."""
    calls = []

    def fake(*args, **kwargs):
        calls.append(args[-1] if args else kwargs.get('command'))
        return 'ok'

    import app.dashboard as dashboard
    import app.server as server
    monkeypatch.setattr(dashboard, '_rcon', lambda cmd: fake(cmd))
    monkeypatch.setattr(server, '_rcon', lambda cmd: fake(cmd))
    return calls


def csrf_token_from(html: bytes) -> str:
    m = re.search(rb'name="csrf_token" value="([^"]+)"', html) or \
        re.search(rb'name="csrf-token" content="([^"]+)"', html)
    assert m, 'no CSRF token in page'
    return m.group(1).decode()
