import io
import os
import tarfile

import pytest


@pytest.fixture
def plugins_dir(app):
    root = os.path.join(app.config['CS2_DATA_PATH'], 'game', 'csgo', 'addons',
                        'counterstrikesharp', 'plugins')
    foo = os.path.join(root, 'Foo')
    foo2 = os.path.join(root, 'Foo2')
    os.makedirs(foo)
    os.makedirs(foo2)
    with open(os.path.join(foo, 'config.json'), 'w') as fh:
        fh.write('{"a": 1}')
    with open(os.path.join(foo2, 'secret.cfg'), 'w') as fh:
        fh.write('original')
    return root


def test_edit_cannot_read_sibling_with_shared_prefix(login_as, plugins_dir):
    resp = login_as('admin').get('/plugins/edit/Foo?file=../Foo2/secret.cfg')
    assert resp.status_code == 302
    assert b'original' not in resp.data


def test_save_cannot_write_sibling_with_shared_prefix(login_as, plugins_dir):
    resp = login_as('admin').post('/plugins/edit/Foo/save', data={
        'file': '../Foo2/secret.cfg', 'content': 'pwned'})
    assert resp.status_code == 403
    with open(os.path.join(plugins_dir, 'Foo2', 'secret.cfg')) as fh:
        assert fh.read() == 'original'


def test_save_cannot_escape_with_dotdot(login_as, plugins_dir):
    resp = login_as('admin').post('/plugins/edit/Foo/save', data={
        'file': '../../../../../../cfg/server.cfg', 'content': 'pwned'})
    assert resp.status_code == 403


def test_save_valid_config_is_audited(app, login_as, plugins_dir):
    from app.models import get_audit_logs
    resp = login_as('admin').post('/plugins/edit/Foo/save', data={
        'file': 'config.json', 'content': '{"a": 2}'})
    assert resp.status_code == 200
    with open(os.path.join(plugins_dir, 'Foo', 'config.json')) as fh:
        assert fh.read() == '{"a": 2}'
    assert get_audit_logs(app.config['DATABASE'])[0]['action'] == 'Plugin Config Saved'


def test_plugin_name_with_trailing_newline_rejected():
    from app.plugins import _safe_plugin_name
    assert _safe_plugin_name('Foo')
    assert not _safe_plugin_name('Foo\n')
    assert not _safe_plugin_name('../Foo')


def _tar_with_symlink(path, target):
    with tarfile.open(path, 'w:gz') as tar:
        info = tarfile.TarInfo('evil.cfg')
        info.type = tarfile.SYMTYPE
        info.linkname = target
        tar.addfile(info)
        data = b'hello'
        info = tarfile.TarInfo('ok.txt')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def test_plugin_tar_with_escaping_symlink_is_rejected(app, tmp_path):
    from app.plugins import _extract_to_tmp
    archive = tmp_path / 'evil.tar.gz'
    _tar_with_symlink(str(archive), '/etc/passwd')
    with app.app_context():
        tmp_dir, error = _extract_to_tmp(str(archive))
    assert tmp_dir is None
    assert error


def test_metamod_tar_with_escaping_symlink_is_rejected(app, tmp_path):
    from app.metamod import _extract_tarball
    archive = tmp_path / 'mm.tar.gz'
    with tarfile.open(str(archive), 'w:gz') as tar:
        info = tarfile.TarInfo('addons/metamod/evil')
        info.type = tarfile.SYMTYPE
        info.linkname = '../../../../../etc/passwd'
        tar.addfile(info)
    with app.app_context():
        ok, _ = _extract_tarball(str(archive), 'test-build')
    assert not ok
    assert not os.path.lexists(os.path.join(
        app.config['CS2_DATA_PATH'], 'game', 'csgo', 'addons', 'metamod', 'evil'))


def test_metamod_ignores_paths_that_only_share_addons_prefix(app, tmp_path):
    from app.metamod import _extract_tarball
    archive = tmp_path / 'mm.tar.gz'
    with tarfile.open(str(archive), 'w:gz') as tar:
        for name in ('addons/metamod/ok.txt', 'addonsEVIL/x.txt'):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b'x'))
    with app.app_context():
        ok, _ = _extract_tarball(str(archive), 'test-build')
    csgo = os.path.join(app.config['CS2_DATA_PATH'], 'game', 'csgo')
    assert ok
    assert os.path.exists(os.path.join(csgo, 'addons', 'metamod', 'ok.txt'))
    assert not os.path.exists(os.path.join(csgo, 'addonsEVIL'))


def test_upload_size_limit(app, login_as):
    app.config['MAX_CONTENT_LENGTH'] = 1024
    resp = login_as('admin').post('/maps/upload', data={
        'map_file': (io.BytesIO(b'x' * 4096), 'big.bsp')},
        content_type='multipart/form-data')
    assert resp.status_code in (302, 413)
    maps_dir = os.path.join(app.config['CS2_DATA_PATH'], 'game', 'csgo', 'maps')
    assert not os.path.exists(os.path.join(maps_dir, 'big.bsp'))
