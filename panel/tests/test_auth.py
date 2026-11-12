import logging

import pytest

from app.models import get_user_by_username
from conftest import ADMIN_PASS, ADMIN_USER, login, make_app


def test_login_redirects_to_safe_next(app):
    resp = login(app.test_client(), ADMIN_USER, ADMIN_PASS, next_url='/maps/')
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/maps/'


@pytest.mark.parametrize('evil', [
    'https://evil.example',
    '//evil.example',
    '/\\evil.example',
])
def test_login_ignores_offsite_next(app, evil):
    resp = login(app.test_client(), ADMIN_USER, ADMIN_PASS, next_url=evil)
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/'


def test_set_language_ignores_offsite_next(app):
    resp = app.test_client().get('/set_language/tr?next=//evil.example')
    assert resp.headers['Location'] == '/'


def test_set_language_keeps_local_next(app):
    resp = app.test_client().get('/set_language/tr?next=/maps/')
    assert resp.headers['Location'] == '/maps/'


def test_wrong_password_rejected(app):
    client = app.test_client()
    resp = login(client, ADMIN_USER, 'wrong-password')
    assert resp.status_code == 200
    assert client.get('/').status_code == 302  # still anonymous


def test_logout_requires_post(login_as):
    client = login_as('admin')
    assert client.get('/logout').status_code == 405
    assert client.post('/logout').status_code == 302
    assert client.get('/').headers['Location'].startswith('/login')


def test_security_headers(app):
    resp = app.test_client().get('/login')
    assert resp.headers['X-Frame-Options'] == 'DENY'
    assert resp.headers['X-Content-Type-Options'] == 'nosniff'


# ── SECRET_KEY / bootstrap admin ──────────────────────────────────────────────

@pytest.mark.parametrize('key', [
    '', 'short', 'dev-secret-key-change-in-prod', 'please-change-this-to-a-random-secret-key',
    'change-this-to-a-long-random-secret-key',
])
def test_refuses_insecure_secret_key(tmp_path, key):
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        make_app(tmp_path, TESTING=False, SECRET_KEY=key)


def test_accepts_strong_secret_key(tmp_path):
    app = make_app(tmp_path, TESTING=False, SECRET_KEY='x' * 64)
    assert app.config['SECRET_KEY'] == 'x' * 64


def test_generates_admin_password_when_unset(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('PANEL_ADMIN_USER', 'boss')
    monkeypatch.delenv('PANEL_ADMIN_PASS', raising=False)
    with caplog.at_level(logging.WARNING):
        app = make_app(tmp_path)
    record = next(r for r in caplog.records if 'generated password' in r.getMessage())
    generated = record.args[1]
    assert len(generated) >= 12
    assert generated != 'changeme'
    user = get_user_by_username(app.config['DATABASE'], 'boss')
    assert user.role == 'admin'
    assert user.check_password(generated)


def test_bootstrap_admin_only_when_no_users(tmp_path, monkeypatch):
    monkeypatch.setenv('PANEL_ADMIN_USER', 'first')
    monkeypatch.setenv('PANEL_ADMIN_PASS', 'first-pass-123')
    app = make_app(tmp_path)
    monkeypatch.setenv('PANEL_ADMIN_USER', 'second')
    monkeypatch.setenv('PANEL_ADMIN_PASS', 'second-pass-123')
    make_app(tmp_path)  # restart with different env
    assert get_user_by_username(app.config['DATABASE'], 'second') is None
    assert get_user_by_username(app.config['DATABASE'], 'first').check_password('first-pass-123')


def test_bootstrap_admin_is_race_safe(tmp_path):
    """Gunicorn workers bootstrap concurrently; only one may create the admin.

    Regression test: two workers both saw an empty table, both inserted, and
    the loser crashed with IntegrityError, taking gunicorn down with it.
    """
    import threading
    from app.models import init_db, get_all_users, get_or_create_admin
    db = str(tmp_path / 'race.db')
    init_db(db)
    workers = 6
    barrier = threading.Barrier(workers)
    results, errors = [], []

    def worker():
        barrier.wait()
        try:
            results.append(get_or_create_admin(db, 'admin', 'race-pass-123'))
        except Exception as exc:  # pragma: no cover - this is the failure mode
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert results.count(True) == 1
    assert len(get_all_users(db)) == 1


# ── Session invalidation ──────────────────────────────────────────────────────

def test_password_change_revokes_other_sessions(app, make_user):
    make_user('alice', 'viewer')
    laptop, phone = app.test_client(), app.test_client()
    login(laptop, 'alice')
    login(phone, 'alice')
    user_id = get_user_by_username(app.config['DATABASE'], 'alice').id

    resp = laptop.post(f'/users/change_password/{user_id}', data={
        'current_password': 'secret-pass-123', 'new_password': 'brand-new-pass-1',
    })
    assert resp.status_code == 302

    assert laptop.get('/users/').status_code == 200          # stays logged in
    assert phone.get('/users/').headers['Location'].startswith('/login')  # kicked out


def test_legacy_session_id_is_rejected(app):
    from app.models import load_user_from_session_id
    db = app.config['DATABASE']
    assert load_user_from_session_id(db, '1') is None          # pre-upgrade format
    assert load_user_from_session_id(db, '1:deadbeef') is None
    assert load_user_from_session_id(db, 'x:y') is None
    admin = get_user_by_username(db, ADMIN_USER)
    assert load_user_from_session_id(db, admin.get_id()).id == admin.id
