import json
import os
import re
import zipfile

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app,
)
from flask_login import login_required, current_user
from flask_babel import _
from werkzeug.utils import secure_filename
from .models import get_state, set_state, log_action

maps_bp = Blueprint('maps', __name__, url_prefix='/maps')

ALLOWED_EXTENSIONS = {'.bsp', '.vpk', '.zip'}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MB


def _maps_dir() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'maps')


def _mapcycle_path() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'mapcycle.txt')


# CS2 default maps — packed into VPK archives, always available
_CS2_DEFAULT_MAPS = [
    'ar_baggage', 'ar_shoots',
    'cs_italy', 'cs_office',
    'de_ancient', 'de_anubis', 'de_cache', 'de_cbble',
    'de_dust2', 'de_inferno', 'de_mirage', 'de_nuke',
    'de_overpass', 'de_train', 'de_vertigo',
]


def _list_maps() -> list[str]:
    """Return available maps: default CS2 maps + any custom .bsp/.vpk files."""
    found: set[str] = set(_CS2_DEFAULT_MAPS)
    d = _maps_dir()
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith('.bsp'):
                found.add(f[:-4])
            elif f.endswith('.vpk') and not f.endswith('_dir.vpk'):
                # e.g. de_dust2.vpk
                found.add(f[:-4])
    return sorted(found)


def _read_mapcycle() -> list[str]:
    path = _mapcycle_path()
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith('//')]


def _write_mapcycle(maps: list[str]) -> None:
    path = _mapcycle_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        for m in maps:
            f.write(m + '\n')


def _get_quick_maps(db: str) -> list[str]:
    _defaults = [
        'de_dust2', 'de_mirage', 'de_inferno', 'de_nuke', 'de_ancient',
        'de_anubis', 'de_vertigo', 'de_overpass', 'cs_office', 'cs_italy',
    ]
    raw = get_state(db, 'quick_maps', '')
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return _defaults


def _set_quick_maps(db: str, maps_list: list[str]) -> None:
    set_state(db, 'quick_maps', json.dumps(maps_list))


# ── Routes ─────────────────────────────────────────────────────────────────────

@maps_bp.route('/debug')
@login_required
def debug():
    maps_dir = _maps_dir()
    return {
        'cs2_data_path': current_app.config['CS2_DATA_PATH'],
        'maps_dir': maps_dir,
        'maps_dir_exists': os.path.isdir(maps_dir),
        'maps_dir_contents': os.listdir(maps_dir)[:30] if os.path.isdir(maps_dir) else [],
        'default_maps_count': len(_CS2_DEFAULT_MAPS),
        'list_maps_result': _list_maps(),
    }


@maps_bp.route('/')
@login_required
def index():
    db = current_app.config['DATABASE']
    return render_template(
        'maps.html',
        maps=_list_maps(),
        mapcycle=_read_mapcycle(),
        quick_maps=_get_quick_maps(db),
        server_ip=current_app.config['SERVER_IP'],
        server_port=current_app.config['CS2_PORT'],
        active='maps',
    )


@maps_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'map_file' not in request.files or not request.files['map_file'].filename:
        flash(_('No file selected.'), 'danger')
        return redirect(url_for('maps.index'))

    f = request.files['map_file']
    filename = secure_filename(f.filename)
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        flash(_('Only .bsp, .vpk or .zip files are accepted.'), 'danger')
        return redirect(url_for('maps.index'))

    maps_dir = _maps_dir()
    os.makedirs(maps_dir, exist_ok=True)

    if ext == '.zip':
        # Extract .bsp and .vpk files from zip
        try:
            zf = zipfile.ZipFile(f)
        except zipfile.BadZipFile:
            flash(_('Invalid ZIP file.'), 'danger')
            return redirect(url_for('maps.index'))
        extracted = []
        for member in zf.namelist():
            member_ext = os.path.splitext(member)[1].lower()
            if member_ext not in ('.bsp', '.vpk'):
                continue
            # Only the filename, no subdirectory traversal
            member_filename = secure_filename(os.path.basename(member))
            if not member_filename:
                continue
            dest = os.path.join(maps_dir, member_filename)
            if not os.path.realpath(dest).startswith(os.path.realpath(maps_dir)):
                continue
            data = zf.read(member)
            with open(dest, 'wb') as out:
                out.write(data)
            extracted.append(member_filename)
        zf.close()
        if extracted:
            log_action(current_app.config['DATABASE'], current_user.username, 'Harita Yüklendi', ', '.join(extracted))
            flash(_('Extracted from ZIP: %(files)s', files=', '.join(extracted)), 'success')
        else:
            flash(_('No .bsp or .vpk found in ZIP.'), 'warning')
        return redirect(url_for('maps.index'))

    save_path = os.path.join(maps_dir, filename)
    # Path traversal guard
    if not os.path.realpath(save_path).startswith(os.path.realpath(maps_dir)):
        flash(_('Security error: invalid file path.'), 'danger')
        return redirect(url_for('maps.index'))

    f.save(save_path)
    log_action(current_app.config['DATABASE'], current_user.username, 'Harita Yüklendi', filename)
    flash(_('Map %(f)s uploaded.', f=filename), 'success')
    return redirect(url_for('maps.index'))


@maps_bp.route('/delete/<map_name>', methods=['POST'])
@login_required
def delete_map(map_name):
    if not re.match(r'^[a-zA-Z0-9_\-]+$', map_name):
        flash(_('Invalid map name.'), 'danger')
        return redirect(url_for('maps.index'))

    maps_dir = _maps_dir()
    real_maps_dir = os.path.realpath(maps_dir)

    deleted = False
    for ext_try in ('.bsp', '.vpk'):
        candidate = os.path.join(maps_dir, map_name + ext_try)
        if not os.path.realpath(candidate).startswith(real_maps_dir):
            flash(_('Security error.'), 'danger')
            return redirect(url_for('maps.index'))
        if os.path.isfile(candidate):
            os.remove(candidate)
            deleted = True
            break

    if deleted:
        cycle = _read_mapcycle()
        if map_name in cycle:
            cycle.remove(map_name)
            _write_mapcycle(cycle)
        log_action(current_app.config['DATABASE'], current_user.username, 'Harita Silindi', map_name)
        flash(_('%(m)s deleted.', m=map_name), 'success')
    else:
        flash(_('Map file not found (.bsp/.vpk).'), 'warning')

    return redirect(url_for('maps.index'))


@maps_bp.route('/mapcycle/toggle', methods=['POST'])
@login_required
def toggle_mapcycle():
    map_name = request.form.get('map_name', '').strip()
    if not re.match(r'^[a-zA-Z0-9_\-]+$', map_name):
        flash(_('Invalid map name.'), 'danger')
        return redirect(url_for('maps.index'))

    cycle = _read_mapcycle()
    if map_name in cycle:
        cycle.remove(map_name)
        flash(_('%(m)s removed from mapcycle.', m=map_name), 'info')
    else:
        cycle.append(map_name)
        flash(_('%(m)s added to mapcycle.', m=map_name), 'success')

    _write_mapcycle(cycle)
    log_action(current_app.config['DATABASE'], current_user.username,
               'Mapcycle Güncellendi', map_name)
    return redirect(url_for('maps.index'))


@maps_bp.route('/quickmap/toggle', methods=['POST'])
@login_required
def toggle_quickmap():
    map_name = request.form.get('map_name', '').strip()
    if not re.match(r'^[a-zA-Z0-9_\-]+$', map_name):
        flash(_('Invalid map name.'), 'danger')
        return redirect(url_for('maps.index'))

    db = current_app.config['DATABASE']
    qmaps = _get_quick_maps(db)
    if map_name in qmaps:
        qmaps.remove(map_name)
        flash(_('%(m)s removed from quick menu.', m=map_name), 'info')
    else:
        qmaps.append(map_name)
        flash(_('%(m)s added to quick menu.', m=map_name), 'success')

    _set_quick_maps(db, qmaps)
    return redirect(url_for('maps.index'))
