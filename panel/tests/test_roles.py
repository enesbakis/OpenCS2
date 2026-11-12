import pytest

# Endpoints intentionally reachable without a role decorator.
PUBLIC_OR_SELF_SERVICE = {
    'static',
    'health',
    'set_language',
    'auth.login',
    'auth.logout',          # login_required only
    'users.index',          # shows only the caller's own account to non-admins
    'users.change_password',  # self or admin, enforced inside the view
}


def test_every_route_declares_a_role(app):
    """Guard: a new route must either use @role_required or be allow-listed."""
    missing = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in PUBLIC_OR_SELF_SERVICE:
            continue
        view = app.view_functions[rule.endpoint]
        if not getattr(view, 'required_role', None):
            missing.append(rule.endpoint)
    assert missing == [], f'routes without @role_required: {sorted(missing)}'


# (role, method, url, kwargs, allowed)
CASES = [
    # admin-only
    ('operator', 'post', '/api/rcon', {'json': {'cmd': 'status'}}, False),
    ('viewer', 'post', '/api/rcon', {'json': {'cmd': 'status'}}, False),
    ('admin', 'post', '/api/rcon', {'json': {'cmd': 'status'}}, True),
    ('operator', 'post', '/api/restart_server', {'json': {}}, False),
    ('admin', 'post', '/api/restart_server', {'json': {}}, True),
    # operator
    ('viewer', 'post', '/change_map', {'data': {'map_name': 'de_dust2'}}, False),
    ('operator', 'post', '/change_map', {'data': {'map_name': 'de_dust2'}}, True),
    ('viewer', 'post', '/server/set_hostname', {'data': {'hostname': 'My Server'}}, False),
    ('operator', 'post', '/server/set_hostname', {'data': {'hostname': 'My Server'}}, True),
    ('viewer', 'post', '/player_action', {'data': {'action': 'kick', 'userid': '3'}}, False),
    ('operator', 'post', '/player_action', {'data': {'action': 'kick', 'userid': '3'}}, True),
]


@pytest.mark.parametrize('role, method, url, kwargs, allowed', CASES)
def test_rcon_routes_respect_roles(login_as, rcon_calls, role, method, url, kwargs, allowed):
    client = login_as(role)
    resp = getattr(client, method)(url, **kwargs)
    if allowed:
        assert rcon_calls, f'{role} should be able to {url}'
    else:
        assert rcon_calls == [], f'{role} must not reach RCON via {url}'
        if 'json' in kwargs:
            assert resp.status_code == 403
            assert resp.get_json()['ok'] is False
        else:
            assert resp.status_code == 302


@pytest.mark.parametrize('role, allowed', [('viewer', False), ('operator', False), ('admin', True)])
def test_server_cfg_write_is_admin_only(app, login_as, rcon_calls, role, allowed):
    import os
    client = login_as(role)
    client.post('/server/save_cfg', data={'cfg_content': 'rcon_password pwned'})
    cfg = os.path.join(app.config['CS2_DATA_PATH'], 'game', 'csgo', 'cfg', 'server.cfg')
    assert os.path.exists(cfg) is allowed


@pytest.mark.parametrize('role, status', [('viewer', 302), ('operator', 302), ('admin', 200)])
def test_audit_log_is_admin_only(login_as, role, status):
    assert login_as(role).get('/audit/').status_code == status


def test_viewer_can_read_lists(login_as):
    client = login_as('viewer')
    assert client.get('/plugins/').status_code == 200
    assert client.get('/csadmins/').status_code == 200


def test_unknown_role_gets_no_access(app, make_user):
    from conftest import login
    from app.models import _get_db
    make_user('ghost', 'viewer')
    with _get_db(app.config['DATABASE']) as conn:
        conn.execute("UPDATE users SET role = 'superuser' WHERE username = 'ghost'")
        conn.commit()
    client = app.test_client()
    login(client, 'ghost')
    assert client.get('/').status_code == 403
    assert client.get('/plugins/').status_code == 302


def test_operator_cannot_inject_console_commands_via_hostname(login_as, rcon_calls):
    client = login_as('operator')
    client.post('/server/set_hostname', data={'hostname': 'x"; rcon_password pwned; "'})
    client.post('/server/set_hostname', data={'hostname': 'x\nrcon_password pwned'})
    assert rcon_calls == []


def test_operator_cannot_inject_via_server_password(login_as, rcon_calls):
    client = login_as('operator')
    client.post('/set_password', data={'password': 'a"\nrcon_password pwned'})
    assert rcon_calls == []
    client.post('/set_password', data={'password': 'hunter2'})
    assert rcon_calls == ['sv_password "hunter2"']


def test_player_id_must_be_ascii_digits(login_as, rcon_calls):
    client = login_as('operator')
    client.post('/player_action', data={'action': 'kick', 'userid': '²'})
    assert rcon_calls == []


@pytest.mark.parametrize('role, visible', [('viewer', False), ('operator', True), ('admin', True)])
def test_join_password_only_shown_to_operators(login_as, monkeypatch, role, visible):
    import app.dashboard as dashboard
    secret = 'JoinPw-7f3a91'
    monkeypatch.setattr(dashboard, '_rcon', lambda cmd: 'status-output')
    monkeypatch.setattr(dashboard, 'parse_status', lambda raw: {
        'hostname': 'Test', 'map': 'de_dust2', 'player_count': 0, 'max_players': 10,
        'bot_count': 0, 'players': []})
    monkeypatch.setattr(dashboard, 'get_cvar',
                        lambda host, port, pw, cvar: secret if cvar == 'sv_password' else '5')
    html = login_as(role).get('/').data.decode()
    assert (secret in html) is visible


def test_rcon_command_is_audited(app, login_as, rcon_calls):
    from app.models import get_audit_logs
    login_as('admin').post('/api/rcon', json={'cmd': 'mp_restartgame 1'})
    entry = get_audit_logs(app.config['DATABASE'])[0]
    assert entry['action'] == 'RCON Command'
    assert entry['detail'] == 'mp_restartgame 1'
