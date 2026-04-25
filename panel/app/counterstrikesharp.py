import json
import os
import re
import tempfile
import urllib.request
import zipfile

from flask import Blueprint, render_template, current_app, request, jsonify
from flask_login import login_required
from werkzeug.utils import secure_filename

css_bp = Blueprint('css', __name__, url_prefix='/counterstrikesharp')

_GH_API_URL = 'https://api.github.com/repos/roflmuffin/CounterStrikeSharp/releases/latest'
_VERSION_FILE = 'addons/.css_installed_version'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _csgo_dir() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo')


def _is_installed() -> bool:
    return os.path.isdir(os.path.join(_csgo_dir(), 'addons', 'counterstrikesharp'))


def _metamod_installed() -> bool:
    return os.path.isdir(os.path.join(_csgo_dir(), 'addons', 'metamod'))


def _installed_version() -> str | None:
    ver_file = os.path.join(_csgo_dir(), _VERSION_FILE)
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            return f.read().strip() or None
    return None


def _get_latest_release() -> tuple[str | None, str | None, str | None]:
    """Return (download_url, version_tag, error_detail) for with-runtime linux build."""
    try:
        req = urllib.request.Request(
            _GH_API_URL,
            headers={
                'User-Agent': 'cs2-panel/1.0',
                'Accept': 'application/vnd.github.v3+json',
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return None, None, f'{type(e).__name__}: {e}'

    tag = data.get('tag_name', '')
    assets = data.get('assets', [])

    # Önce: with-runtime linux (önerilen)
    for asset in assets:
        name = asset.get('name', '')
        if re.match(r'counterstrikesharp-with-runtime-linux-.*\.zip', name):
            return asset['browser_download_url'], tag, None

    # Fallback: sade linux build
    for asset in assets:
        name = asset.get('name', '')
        if re.match(r'counterstrikesharp-linux-.*\.zip', name):
            return asset['browser_download_url'], tag, None

    return None, None, "GitHub release'inde Linux zip bulunamadı"


def _extract_zip(tmp_path: str, version_tag: str) -> tuple[bool, str]:
    """Extract CSS zip into game/csgo/. Only addons/ and gamedata/ trees."""
    csgo = _csgo_dir()
    os.makedirs(csgo, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            for member in zf.infolist():
                norm = os.path.normpath(member.filename)
                if norm.startswith('..') or os.path.isabs(norm):
                    continue
                top = norm.split(os.sep)[0]
                if top not in ('addons', 'gamedata'):
                    continue
                dest = os.path.join(csgo, norm)
                if member.is_dir():
                    os.makedirs(dest, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
    except Exception as e:
        return False, f'Çıkarma hatası: {e}'

    # Sürüm dosyasını yaz
    ver_file = os.path.join(csgo, _VERSION_FILE)
    os.makedirs(os.path.dirname(ver_file), exist_ok=True)
    with open(ver_file, 'w') as f:
        f.write(version_tag)

    return True, version_tag


def _do_install() -> tuple[bool, str]:
    url, version_tag, err = _get_latest_release()
    if not url:
        return False, f"İndirme URL'si alınamadı: {err or 'internet bağlantısını kontrol edin'}"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp_path = tmp.name
        urllib.request.urlretrieve(url, tmp_path)
        return _extract_zip(tmp_path, version_tag or 'bilinmiyor')
    except Exception as e:
        return False, f'İndirme hatası: {e}'
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Routes ─────────────────────────────────────────────────────────────────────

@css_bp.route('/')
@login_required
def index():
    return render_template(
        'counterstrikesharp.html',
        installed=_is_installed(),
        version=_installed_version(),
        metamod_ok=_metamod_installed(),
        active='css',
    )


@css_bp.route('/api/latest')
@login_required
def api_latest():
    url, tag, err = _get_latest_release()
    return jsonify({'url': url, 'tag': tag, 'error': err})


@css_bp.route('/install_upload', methods=['POST'])
@login_required
def install_upload():
    """Browser-fetch indirip gönderilen .zip'i kurar. JSON döner."""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(ok=False, msg='Dosya alınamadı'), 400

    filename = secure_filename(f.filename)
    if not filename.lower().endswith('.zip'):
        return jsonify(ok=False, msg='Yalnızca .zip dosyası kabul edilir'), 400

    # Sürümü dosya adından çıkar
    version_tag = filename
    m = re.search(r'-(v?\d[\d.]+\d)\.zip$', filename, re.IGNORECASE)
    if m:
        version_tag = m.group(1)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp_path = tmp.name
        f.save(tmp_path)
        ok, msg = _extract_zip(tmp_path, version_tag)
        return jsonify(ok=ok, msg=msg), (200 if ok else 500)
    except Exception as e:
        return jsonify(ok=False, msg=str(e)), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
