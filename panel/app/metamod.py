import os
import re
import tarfile
import tempfile
import urllib.request

from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify
from flask_login import login_required, current_user
from flask_babel import _
from werkzeug.utils import secure_filename

from .models import log_action

metamod_bp = Blueprint('metamod', __name__, url_prefix='/metamod')

_DROP_BASE = 'https://mms.alliedmods.net/mmsdrop/2.0/'
_LATEST_ALIAS = 'https://mms.alliedmods.net/mmsdrop/2.0/mmsource-latest-linux'
_VERSION_FILE = 'addons/.metamod_installed_version'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _csgo_dir() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo')


def _is_installed() -> bool:
    return os.path.isdir(os.path.join(_csgo_dir(), 'addons', 'metamod'))


def _gameinfo_patched() -> bool:
    path = os.path.join(_csgo_dir(), 'gameinfo.gi')
    if not os.path.isfile(path):
        return False
    with open(path, encoding='utf-8', errors='replace') as f:
        return 'csgo/addons/metamod' in f.read()


def _installed_version() -> str | None:
    ver_file = os.path.join(_csgo_dir(), _VERSION_FILE)
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            return f.read().strip() or None
    return None


def _get_latest_url() -> tuple[str | None, str | None, str | None]:
    """Return (download_url, build_name, error_detail)."""
    # Strategy 1: direct "latest" alias URL
    try:
        req = urllib.request.Request(
            _LATEST_ALIAS, method='HEAD',
            headers={'User-Agent': 'cs2-panel/1.0'},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            final_url = resp.url  # may redirect to real versioned filename
        build = final_url.split('/')[-1]
        return final_url, build, None
    except Exception as e1:
        pass

    # Strategy 2: scrape directory listing
    try:
        req = urllib.request.Request(_DROP_BASE, headers={'User-Agent': 'cs2-panel/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        matches = re.findall(r'(mmsource-[^"]*-linux\.tar\.gz)', html)
        if matches:
            build = matches[-1]
            return _DROP_BASE + build, build, None
        return None, None, 'Dizin listesi alındı fakat uygun dosya bulunamadı'
    except Exception as e2:
        return None, None, f'{type(e2).__name__}: {e2}'


def _patch_gameinfo() -> tuple[bool, str]:
    path = os.path.join(_csgo_dir(), 'gameinfo.gi')
    if not os.path.isfile(path):
        return False, 'gameinfo.gi dosyası bulunamadı'

    with open(path, encoding='utf-8', errors='replace') as f:
        content = f.read()

    if 'csgo/addons/metamod' in content:
        return True, 'gameinfo.gi zaten yamalı'

    # Add metamod entry right before the first "Game    csgo" (no slash after csgo)
    new_content, n = re.subn(
        r'([ \t]+Game[ \t]+csgo)(?![\w/])',
        r'\t\t\t\tGame\t\t\t\tcsgo/addons/metamod\n\1',
        content,
        count=1,
    )
    if n == 0:
        return False, 'gameinfo.gi içinde SearchPaths girdisi bulunamadı — manuel ekleme gerekebilir'

    # Backup original
    with open(path + '.bak', 'w', encoding='utf-8') as f:
        f.write(content)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True, 'gameinfo.gi başarıyla yamalandı (.bak yedek oluşturuldu)'


def _extract_tarball(tmp_path: str, build_name: str) -> tuple[bool, str]:
    """Extract a metamod tar.gz into the CS2 addons directory."""
    csgo = _csgo_dir()
    os.makedirs(csgo, exist_ok=True)
    try:
        with tarfile.open(tmp_path, 'r:gz') as tar:
            safe_members = []
            for m in tar.getmembers():
                norm = os.path.normpath(m.name)
                if norm.startswith('..') or os.path.isabs(norm):
                    continue
                if norm.startswith('addons') or norm == 'addons':
                    safe_members.append(m)
            tar.extractall(path=csgo, members=safe_members)
    except Exception as e:
        return False, f'Çıkarma hatası: {e}'

    ver_file = os.path.join(csgo, _VERSION_FILE)
    os.makedirs(os.path.dirname(ver_file), exist_ok=True)
    with open(ver_file, 'w') as f:
        f.write(build_name)

    return True, build_name


def _do_install() -> tuple[bool, str]:
    url, build_name, err = _get_latest_url()
    if not url:
        detail = err or 'internet bağlantısını kontrol edin'
        return False, f'Metamod indirme URL\'si alınamadı: {detail}'

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
            tmp_path = tmp.name
        urllib.request.urlretrieve(url, tmp_path)
        return _extract_tarball(tmp_path, build_name)
    except Exception as e:
        return False, f'İndirme hatası: {e}'
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Routes ─────────────────────────────────────────────────────────────────────

@metamod_bp.route('/')
@login_required
def index():
    installed = _is_installed()
    patched = _gameinfo_patched()
    version = _installed_version()
    gameinfo_exists = os.path.isfile(os.path.join(_csgo_dir(), 'gameinfo.gi'))

    return render_template(
        'metamod.html',
        installed=installed,
        patched=patched,
        version=version,
        gameinfo_exists=gameinfo_exists,
        active='metamod',
    )


@metamod_bp.route('/api/latest')
@login_required
def api_latest():
    url, build, err = _get_latest_url()
    return {'url': url, 'build': build, 'error': err}


@metamod_bp.route('/install', methods=['POST'])
@login_required
def install():
    ok, msg = _do_install()
    if not ok:
        flash(_('Installation failed: %(msg)s', msg=msg), 'danger')
        return redirect(url_for('metamod.index'))

    flash(_('Metamod installed \u2192 %(msg)s', msg=msg), 'success')
    log_action(current_app.config['DATABASE'], current_user.username,
               'Metamod Installed', msg)

    # Auto-patch gameinfo.gi
    ok2, msg2 = _patch_gameinfo()
    flash(_('gameinfo.gi: %(msg)s', msg=msg2), 'success' if ok2 else 'warning')

    return redirect(url_for('metamod.index'))


@metamod_bp.route('/patch', methods=['POST'])
@login_required
def patch():
    ok, msg = _patch_gameinfo()
    flash(msg, 'success' if ok else 'danger')
    if ok:
        log_action(current_app.config['DATABASE'], current_user.username,
                   'gameinfo.gi Yamandı', msg)
    return redirect(url_for('metamod.index'))


@metamod_bp.route('/install_upload', methods=['POST'])
@login_required
def install_upload():
    """
    Accept a tar.gz uploaded from the browser (client-side fetch bypass).
    Returns JSON so the JS caller can handle success/error.
    """
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(ok=False, msg='Dosya alınamadı'), 400

    filename = secure_filename(f.filename)
    if not filename.endswith('.tar.gz'):
        return jsonify(ok=False, msg='Yalnızca .tar.gz dosyası kabul edilir'), 400

    build_name = filename  # e.g. mmsource-2.0.0-git1390-linux.tar.gz

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
            tmp_path = tmp.name
        f.save(tmp_path)

        ok, msg = _extract_tarball(tmp_path, build_name)
        if not ok:
            return jsonify(ok=False, msg=msg), 500

        ok2, msg2 = _patch_gameinfo()
        return jsonify(ok=True, msg=f'Kuruldu: {msg}', patch=msg2)
    except Exception as e:
        return jsonify(ok=False, msg=str(e)), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
