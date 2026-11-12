from app.models import get_user_by_username
from conftest import ADMIN_PASS, ADMIN_USER, PASSWORD, login


def _user(app, name):
    return get_user_by_username(app.config['DATABASE'], name)


def test_operator_cannot_change_other_users_password(app, login_as):
    client = login_as('operator')
    admin_id = _user(app, ADMIN_USER).id
    client.post(f'/users/change_password/{admin_id}', data={'new_password': 'taken-over-123'})
    assert _user(app, ADMIN_USER).check_password(ADMIN_PASS)
    assert not _user(app, ADMIN_USER).check_password('taken-over-123')


def test_self_change_requires_current_password(app, login_as):
    client = login_as('viewer')
    me = _user(app, 'user_viewer')
    client.post(f'/users/change_password/{me.id}', data={
        'current_password': 'wrong', 'new_password': 'another-pass-1'})
    assert _user(app, 'user_viewer').check_password(PASSWORD)

    client.post(f'/users/change_password/{me.id}', data={
        'current_password': PASSWORD, 'new_password': 'another-pass-1'})
    assert _user(app, 'user_viewer').check_password('another-pass-1')


def test_password_minimum_length(app, login_as):
    client = login_as('viewer')
    me = _user(app, 'user_viewer')
    client.post(f'/users/change_password/{me.id}', data={
        'current_password': PASSWORD, 'new_password': 'short'})
    assert _user(app, 'user_viewer').check_password(PASSWORD)


def test_admin_can_reset_other_password(app, login_as, make_user):
    make_user('bob', 'viewer')
    login_as('admin').post(f'/users/change_password/{_user(app, "bob").id}',
                           data={'new_password': 'reset-by-admin-1'})
    assert _user(app, 'bob').check_password('reset-by-admin-1')


def test_create_user_defaults_to_viewer_and_validates_role(app, login_as):
    client = login_as('admin')
    client.post('/users/create', data={'username': 'carol', 'password': 'carol-pass-1'})
    assert _user(app, 'carol').role == 'viewer'
    client.post('/users/create', data={'username': 'dave', 'password': 'dave-pass-12', 'role': 'root'})
    assert _user(app, 'dave') is None
    client.post('/users/create', data={'username': 'erin', 'password': 'erin-pass-12', 'role': 'operator'})
    assert _user(app, 'erin').role == 'operator'


def test_non_admin_cannot_create_users_or_change_roles(app, login_as, make_user):
    client = login_as('operator')
    client.post('/users/create', data={'username': 'mallory', 'password': 'mallory-pass', 'role': 'admin'})
    assert _user(app, 'mallory') is None
    me = _user(app, 'user_operator')
    client.post(f'/users/role/{me.id}', data={'role': 'admin'})
    assert _user(app, 'user_operator').role == 'operator'


def test_non_admin_only_sees_own_account(app, login_as, make_user):
    make_user('someone_else', 'viewer')
    html = login_as('operator').get('/users/').data
    assert b'user_operator' in html
    assert b'someone_else' not in html


def test_last_admin_cannot_be_deleted_or_demoted(app, login_as, make_user):
    client = login_as('admin')
    admin_id = _user(app, ADMIN_USER).id
    # Demoting yourself when you are the only admin is refused.
    client.post(f'/users/role/{admin_id}', data={'role': 'viewer'})
    assert _user(app, ADMIN_USER).role == 'admin'

    # With a second admin, the first one can be demoted and then deleted.
    make_user('admin2', 'admin')
    other = app.test_client()
    login(other, 'admin2')
    other.post(f'/users/role/{admin_id}', data={'role': 'viewer'})
    assert _user(app, ADMIN_USER).role == 'viewer'
    other.post(f'/users/delete/{admin_id}')
    assert _user(app, ADMIN_USER) is None


def test_cannot_delete_last_admin_directly(app):
    import pytest
    from app.models import LastAdminError, delete_user
    with pytest.raises(LastAdminError):
        delete_user(app.config['DATABASE'], _user(app, ADMIN_USER).id)


def test_role_change_takes_effect_immediately(app, login_as):
    from app.models import update_role
    client = login_as('operator')
    assert client.get('/server/').status_code in (200, 302)
    update_role(app.config['DATABASE'], _user(app, 'user_operator').id, 'viewer')
    resp = client.post('/change_map', data={'map_name': 'de_dust2'})
    assert resp.status_code == 302
    assert client.get('/server/').headers.get('Location') == '/'
