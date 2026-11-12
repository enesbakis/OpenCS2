from conftest import ADMIN_PASS, ADMIN_USER, csrf_token_from


def _login_with_csrf(client):
    token = csrf_token_from(client.get('/login').data)
    resp = client.post('/login', data={
        'username': ADMIN_USER, 'password': ADMIN_PASS, 'csrf_token': token,
    })
    assert resp.status_code == 302 and resp.headers['Location'] == '/'
    return client


def test_login_without_token_is_rejected(csrf_app):
    client = csrf_app.test_client()
    resp = client.post('/login', data={'username': ADMIN_USER, 'password': ADMIN_PASS})
    assert resp.status_code == 302
    assert client.get('/').headers['Location'].startswith('/login')  # not logged in


def test_login_with_token_succeeds(csrf_app):
    _login_with_csrf(csrf_app.test_client())


def test_form_post_without_token_has_no_effect(csrf_app, rcon_calls):
    client = _login_with_csrf(csrf_app.test_client())
    resp = client.post('/change_map', data={'map_name': 'de_dust2'})
    assert resp.status_code == 302
    assert rcon_calls == []


def test_form_post_with_token_works(csrf_app, rcon_calls):
    client = _login_with_csrf(csrf_app.test_client())
    token = csrf_token_from(client.get('/users/').data)
    client.post('/change_map', data={'map_name': 'de_dust2', 'csrf_token': token})
    assert rcon_calls == ['changelevel de_dust2']


def test_ajax_without_header_gets_json_400(csrf_app, rcon_calls):
    client = _login_with_csrf(csrf_app.test_client())
    resp = client.post('/api/rcon', json={'cmd': 'status'})
    assert resp.status_code == 400
    assert resp.get_json()['ok'] is False
    assert rcon_calls == []


def test_ajax_with_header_works(csrf_app, rcon_calls):
    client = _login_with_csrf(csrf_app.test_client())
    token = csrf_token_from(client.get('/users/').data)
    resp = client.post('/api/rcon', json={'cmd': 'status'}, headers={'X-CSRFToken': token})
    assert resp.status_code == 200
    assert rcon_calls == ['status']


def test_every_post_form_in_templates_has_token(csrf_app):
    """Static guard: no template may add a POST form without a CSRF field."""
    import os
    import re
    tpl_dir = os.path.join(csrf_app.root_path, 'templates')
    for name in os.listdir(tpl_dir):
        src = open(os.path.join(tpl_dir, name), encoding='utf-8').read()
        for m in re.finditer(r'<form\b[^>]*method="post"[^>]*>(.*?)</form>', src, re.I | re.S):
            assert 'csrf_token' in m.group(1), f'{name}: POST form without csrf_token'
