import json
import logging
import os
import re

from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, current_app, request,
)
from flask_login import login_required
from flask_babel import _

logger = logging.getLogger(__name__)


def _rcon_reload_admins() -> None:
    """Send css_admins_reload via RCON. Silently ignore if RCON is unavailable."""
    try:
        from .rcon_client import rcon_execute, RCONError
        host = current_app.config.get('RCON_HOST', '127.0.0.1')
        port = int(current_app.config.get('RCON_PORT', 27015))
        password = current_app.config.get('RCON_PASSWORD', '')
        if not password:
            return
        rcon_execute(host, port, password, 'css_admins_reload', timeout=3)
    except Exception as e:
        logger.debug('RCON css_admins_reload failed (non-critical): %s', e)

csadmins_bp = Blueprint('csadmins', __name__, url_prefix='/csadmins')

# All known CSS permission flags
CSS_FLAGS = [
    ("@css/reservation", "Rezervasyon"),
    ("@css/generic",     "Genel Admin"),
    ("@css/kick",        "Kick"),
    ("@css/ban",         "Ban"),
    ("@css/unban",       "Unban"),
    ("@css/vip",         "VIP"),
    ("@css/slay",        "Slay"),
    ("@css/changemap",   "Harita Değiştir"),
    ("@css/cvar",        "CVar"),
    ("@css/config",      "Config"),
    ("@css/chat",        "Chat"),
    ("@css/vote",        "Oylama"),
    ("@css/password",    "Şifre"),
    ("@css/rcon",        "RCON"),
    ("@css/cheats",      "Cheat"),
    ("@css/root",        "Root (Tüm Yetkiler)"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _configs_dir() -> str:
    return os.path.join(
        current_app.config['CS2_DATA_PATH'],
        'game', 'csgo', 'addons', 'counterstrikesharp', 'configs',
    )


def _admins_path() -> str:
    return os.path.join(_configs_dir(), 'admins.json')


def _groups_path() -> str:
    return os.path.join(_configs_dir(), 'admin_groups.json')


def _load_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _valid_identity(identity: str) -> bool:
    """Accept Steam64 ID (17-digit number) or STEAM_X:X:X format."""
    if re.match(r'^\d{17}$', identity):
        return True
    if re.match(r'^STEAM_[0-5]:[01]:\d+$', identity):
        return True
    return False


def _safe_name(name: str) -> bool:
    return bool(name) and len(name) <= 64


# ── Routes ─────────────────────────────────────────────────────────────────────

@csadmins_bp.route('/')
@login_required
def index():
    admins = _load_json(_admins_path())
    groups = _load_json(_groups_path())
    return render_template(
        'csadmins.html',
        admins=admins,
        groups=groups,
        css_flags=CSS_FLAGS,
        active='csadmins',
    )


@csadmins_bp.route('/add', methods=['POST'])
@login_required
def add():
    name     = request.form.get('name', '').strip()
    identity = request.form.get('identity', '').strip()
    immunity = request.form.get('immunity', '0').strip()
    flags    = request.form.getlist('flags')
    groups   = request.form.getlist('groups')

    if not _safe_name(name):
        flash(_('Invalid name (max 64 characters).'), 'danger')
        return redirect(url_for('csadmins.index'))

    if not _valid_identity(identity):
        flash(_('Invalid Steam ID. Use Steam64 (17 digits) or STEAM_X:X:X format.'), 'danger')
        return redirect(url_for('csadmins.index'))

    try:
        immunity_val = int(immunity)
        if not (0 <= immunity_val <= 255):
            raise ValueError
    except ValueError:
        flash(_('Immunity must be a number between 0 and 255.'), 'danger')
        return redirect(url_for('csadmins.index'))

    admins = _load_json(_admins_path())

    # Check for duplicate identity
    for existing_name, data in admins.items():
        if data.get('identity') == identity:
            flash(f'Bu Steam ID zaten "{existing_name}" olarak kayıtlı.', 'warning')
            return redirect(url_for('csadmins.index'))

    entry: dict = {'identity': identity}
    if immunity_val > 0:
        entry['immunity'] = immunity_val
    if flags:
        entry['flags'] = flags
    if groups:
        entry['groups'] = groups

    admins[name] = entry
    _save_json(_admins_path(), admins)
    _rcon_reload_admins()
    flash(_('Admin "%(n)s" added.', n=name), 'success')
    return redirect(url_for('csadmins.index'))


@csadmins_bp.route('/edit/<path:admin_name>', methods=['GET', 'POST'])
@login_required
def edit(admin_name: str):
    admins = _load_json(_admins_path())
    groups = _load_json(_groups_path())

    if admin_name not in admins:
        flash(_('Admin not found.'), 'warning')
        return redirect(url_for('csadmins.index'))

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        identity = request.form.get('identity', '').strip()
        immunity = request.form.get('immunity', '0').strip()
        flags    = request.form.getlist('flags')
        grps     = request.form.getlist('groups')

        if not _safe_name(new_name):
            flash(_('Invalid name.'), 'danger')
            return redirect(url_for('csadmins.edit', admin_name=admin_name))

        if not _valid_identity(identity):
            flash(_('Invalid Steam ID.'), 'danger')
            return redirect(url_for('csadmins.edit', admin_name=admin_name))

        try:
            immunity_val = int(immunity)
            if not (0 <= immunity_val <= 255):
                raise ValueError
        except ValueError:
            flash(_('Immunity must be between 0 and 255.'), 'danger')
            return redirect(url_for('csadmins.edit', admin_name=admin_name))

        # Check duplicate identity (ignore self)
        for existing_name, data in admins.items():
            if existing_name != admin_name and data.get('identity') == identity:
                flash(_('This Steam ID is already registered as "%(n)s".', n=existing_name), 'warning')
                return redirect(url_for('csadmins.edit', admin_name=admin_name))

        entry: dict = {'identity': identity}
        if immunity_val > 0:
            entry['immunity'] = immunity_val
        if flags:
            entry['flags'] = flags
        if grps:
            entry['groups'] = grps

        # If name changed, remove old key
        if new_name != admin_name:
            del admins[admin_name]
        admins[new_name] = entry

        _save_json(_admins_path(), admins)
        _rcon_reload_admins()
        flash(_('"%(n)s" updated.', n=new_name), 'success')
        return redirect(url_for('csadmins.index'))

    admin_data = admins[admin_name]
    return render_template(
        'csadmin_edit.html',
        admin_name=admin_name,
        admin=admin_data,
        groups=groups,
        css_flags=CSS_FLAGS,
        active='csadmins',
    )


@csadmins_bp.route('/delete/<path:admin_name>', methods=['POST'])
@login_required
def delete(admin_name: str):
    admins = _load_json(_admins_path())

    if admin_name not in admins:
        flash(_('Admin not found.'), 'warning')
        return redirect(url_for('csadmins.index'))

    del admins[admin_name]
    _save_json(_admins_path(), admins)
    _rcon_reload_admins()
    flash(_('"%(n)s" deleted.', n=admin_name), 'success')
    return redirect(url_for('csadmins.index'))


# ── Group Routes ───────────────────────────────────────────────────────────────

@csadmins_bp.route('/groups/add', methods=['POST'])
@login_required
def add_group():
    name     = request.form.get('group_name', '').strip()
    immunity = request.form.get('group_immunity', '0').strip()
    flags    = request.form.getlist('group_flags')

    if not name.startswith('#'):
        name = '#' + name
    if len(name) > 64:
        flash(_('Group name is too long.'), 'danger')
        return redirect(url_for('csadmins.index'))

    try:
        immunity_val = int(immunity)
        if not (0 <= immunity_val <= 255):
            raise ValueError
    except ValueError:
        flash(_('Immunity must be between 0 and 255.'), 'danger')
        return redirect(url_for('csadmins.index'))

    groups = _load_json(_groups_path())
    if name in groups:
        flash(_('Group "%(n)s" already exists.', n=name), 'warning')
        return redirect(url_for('csadmins.index'))

    entry: dict = {}
    if flags:
        entry['flags'] = flags
    if immunity_val > 0:
        entry['immunity'] = immunity_val

    groups[name] = entry
    _save_json(_groups_path(), groups)
    _rcon_reload_admins()
    flash(_('Group "%(n)s" created.', n=name), 'success')
    return redirect(url_for('csadmins.index'))


@csadmins_bp.route('/groups/delete/<path:group_name>', methods=['POST'])
@login_required
def delete_group(group_name: str):
    groups = _load_json(_groups_path())
    if group_name not in groups:
        flash(_('Group not found.'), 'warning')
        return redirect(url_for('csadmins.index'))

    del groups[group_name]
    _save_json(_groups_path(), groups)
    _rcon_reload_admins()
    flash(_('Group "%(n)s" deleted.', n=group_name), 'success')
    return redirect(url_for('csadmins.index'))
