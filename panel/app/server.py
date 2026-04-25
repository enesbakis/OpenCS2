import os

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app,
)
from flask_login import login_required, current_user
from flask_babel import _
from .rcon_client import rcon_execute, RCONError
from .models import get_state, set_state, log_action

server_bp = Blueprint('server', __name__, url_prefix='/server')

GAME_MODES = {
    'casual':       {'type': 0, 'mode': 0, 'label': 'Casual'},
    'competitive':  {'type': 0, 'mode': 1, 'label': 'Competitive'},
    'deathmatch':   {'type': 1, 'mode': 2, 'label': 'Deathmatch'},
    'wingman':      {'type': 0, 'mode': 2, 'label': 'Wingman (2v2)'},
}


def _rcon(cmd: str) -> str:
    c = current_app.config
    return rcon_execute(c['RCON_HOST'], c['RCON_PORT'], c['RCON_PASSWORD'], cmd)


def _cfg_path() -> str:
    return os.path.join(
        current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'cfg', 'server.cfg'
    )


def _logs_dir() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'logs')


# ── Routes ─────────────────────────────────────────────────────────────────────

@server_bp.route('/')
@login_required
def index():
    cfg = current_app.config
    db = cfg['DATABASE']
    cfg_path = _cfg_path()
    cfg_content = ''
    if os.path.isfile(cfg_path):
        with open(cfg_path, 'r', errors='replace') as f:
            cfg_content = f.read()

    stored_max = get_state(db, 'max_players', '')
    if not stored_max:
        stored_max = str(cfg.get('CS2_MAXPLAYERS', 16))

    current_hostname = get_state(db, 'hostname', '')

    # current_mode: read game_type + game_mode via RCON, fall back to None
    current_mode = None
    try:
        gt = _rcon('game_type')
        gm = _rcon('game_mode')
        import re
        _vgt = re.search(r'=\s*"?(\d+)', gt)
        _vgm = re.search(r'=\s*"?(\d+)', gm)
        if _vgt and _vgm:
            gt_v, gm_v = int(_vgt.group(1)), int(_vgm.group(1))
            for k, v in GAME_MODES.items():
                if v['type'] == gt_v and v['mode'] == gm_v:
                    current_mode = k
                    break
    except Exception:
        pass

    return render_template(
        'server_settings.html',
        cfg_content=cfg_content,
        cfg_path=_cfg_path(),
        game_modes=GAME_MODES,
        current_mode=current_mode,
        server_ip=cfg['SERVER_IP'],
        server_port=cfg['CS2_PORT'],
        max_players=int(stored_max),
        hostname=current_hostname,
        active='server',
    )


@server_bp.route('/set_hostname', methods=['POST'])
@login_required
def set_hostname():
    name = request.form.get('hostname', '').strip()
    if not name or len(name) > 128:
        flash(_('Invalid server name (1-128 characters).'), 'danger')
        return redirect(url_for('server.index'))
    db = current_app.config['DATABASE']
    try:
        _rcon(f'hostname "{name}"')
        set_state(db, 'hostname', name)
        log_action(db, current_user.username, 'Server Name Changed', name)
        flash(_('Server name \u2192 %(name)s', name=name), 'success')
    except RCONError as exc:
        flash(_('RCON error: %(e)s', e=exc), 'danger')
    return redirect(url_for('server.index'))


@server_bp.route('/set_max_players', methods=['POST'])
@login_required
def set_max_players():
    val = request.form.get('max_players', '').strip()
    if not val.isdigit() or int(val) < 1 or int(val) > 64:
        flash(_('Invalid value. Enter a number between 1 and 64.'), 'danger')
        return redirect(url_for('server.index'))
    db = current_app.config['DATABASE']
    set_state(db, 'max_players', val)
    log_action(db, current_user.username, 'Max Players Changed', f'{val} players')
    flash(_('Maximum player count saved as %(n)s.', n=val), 'success')
    return redirect(url_for('server.index'))


@server_bp.route('/save_cfg', methods=['POST'])
@login_required
def save_cfg():
    content = request.form.get('cfg_content', '')
    cfg_path = _cfg_path()
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, 'w') as f:
        f.write(content)
    try:
        _rcon('exec server.cfg')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'server.cfg Saved', 'Loaded via RCON')
        flash(_('server.cfg saved and loaded.'), 'success')
    except RCONError:
        log_action(current_app.config['DATABASE'], current_user.username,
                   'server.cfg Saved', 'Without RCON')
        flash(_('server.cfg saved \u2014 could not exec via RCON.'), 'warning')
    return redirect(url_for('server.index'))


@server_bp.route('/set_gamemode', methods=['POST'])
@login_required
def set_gamemode():
    key = request.form.get('gamemode', '')
    if key not in GAME_MODES:
        flash(_('Invalid game mode.'), 'danger')
        return redirect(url_for('server.index'))
    m = GAME_MODES[key]
    try:
        _rcon(f'game_type {m["type"]}')
        _rcon(f'game_mode {m["mode"]}')
        _rcon('mp_restartgame 1')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Game Mode Changed', m['label'])
        flash(_('Game mode \u2192 %(m)s', m=m["label"]), 'success')
    except RCONError as exc:
        flash(_('RCON error: %(e)s', e=exc), 'danger')
    return redirect(url_for('server.index'))


@server_bp.route('/logs')
@login_required
def logs():
    logs_dir = _logs_dir()
    log_files = []
    log_content = ''
    selected = request.args.get('file', '')

    if os.path.isdir(logs_dir):
        log_files = sorted(
            [f for f in os.listdir(logs_dir) if f.endswith('.log')],
            reverse=True,
        )

    if not selected and log_files:
        selected = log_files[0]

    if selected:
        safe = os.path.realpath(os.path.join(logs_dir, os.path.basename(selected)))
        if safe.startswith(os.path.realpath(logs_dir)) and os.path.isfile(safe):
            with open(safe, 'r', errors='replace') as f:
                lines = f.readlines()
            log_content = ''.join(lines[-300:])
        else:
            flash(_('Invalid log file.'), 'danger')

    return render_template(
        'logs.html',
        log_files=log_files,
        selected_file=selected,
        log_content=log_content,
        server_ip=current_app.config['SERVER_IP'],
        server_port=current_app.config['CS2_PORT'],
        active='logs',
    )
