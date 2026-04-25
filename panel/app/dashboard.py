import json
import os
import re
from datetime import datetime, timezone

import psutil
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app,
)
from flask_login import login_required, current_user
from flask_babel import _

from .models import get_state, set_state, log_action
from .rcon_client import rcon_execute, parse_status, get_cvar, RCONError

_DEFAULT_QUICK_MAPS = [
    'de_dust2', 'de_mirage', 'de_inferno', 'de_nuke', 'de_ancient',
    'de_anubis', 'de_vertigo', 'de_overpass', 'cs_office', 'cs_italy',
]


def _get_quick_maps(db: str) -> list[str]:
    raw = get_state(db, 'quick_maps', '')
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return list(_DEFAULT_QUICK_MAPS)


dashboard_bp = Blueprint('dashboard', __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _rcon(command: str) -> str:
    c = current_app.config
    return rcon_execute(c['RCON_HOST'], c['RCON_PORT'], c['RCON_PASSWORD'], command)


def _get_next_map(current_map: str) -> str:
    path = os.path.join(
        current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'mapcycle.txt'
    )
    if not os.path.isfile(path):
        return '—'
    with open(path) as f:
        cycle = [ln.strip() for ln in f if ln.strip() and not ln.startswith('//')]
    if not cycle:
        return '—'
    if current_map in cycle:
        return cycle[(cycle.index(current_map) + 1) % len(cycle)]
    return cycle[0]


def _record_online(db: str) -> str:
    """Store/retrieve the timestamp when the server was first seen online."""
    ts = get_state(db, 'online_since')
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()
        set_state(db, 'online_since', ts)
    # Human-readable duration
    try:
        since = datetime.fromisoformat(ts)
        delta = datetime.now(timezone.utc) - since
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        return f'{h} Saat {m} Dakika'
    except Exception:
        return '—'


def _clear_online(db: str) -> None:
    set_state(db, 'online_since', '')


# ── Routes ─────────────────────────────────────────────────────────────────────

@dashboard_bp.route('/')
@login_required
def index():
    cfg = current_app.config
    db = cfg['DATABASE']

    server = {
        'hostname': '—',
        'map': '—',
        'next_map': '—',
        'player_count': 0,
        'max_players': 0,
        'bot_count': 0,
        'players': [],
        'sv_password': '',
        'timelimit': '—',
        'roundtime': '—',
        'uptime': '—',
        'online': False,
        'error': None,
    }

    try:
        raw = _rcon('status')
        parsed = parse_status(raw)
        server.update({
            'hostname': parsed['hostname'],
            'map': parsed['map'],
            'next_map': _get_next_map(parsed['map']),
            'player_count': parsed['player_count'],
            'max_players': parsed['max_players'],
            'bot_count': parsed['bot_count'],
            'players': parsed['players'],
            'online': True,
            'uptime': _record_online(db),
        })

        for cvar, key, fmt in [
            ('mp_timelimit', 'timelimit', '{} Dakika'),
            ('mp_roundtime', 'roundtime', '{} Dakika'),
            ('sv_password', 'sv_password', '{}'),
        ]:
            val = get_cvar(cfg['RCON_HOST'], cfg['RCON_PORT'], cfg['RCON_PASSWORD'], cvar)
            if val is not None:
                server[key] = fmt.format(val) if key != 'sv_password' else val

        # Maksimum oyuncu sayısını DB'den oku (panelden değiştirilebilir)
        stored_max = get_state(db, 'max_players', '')
        if stored_max and stored_max.isdigit() and int(stored_max) > 0:
            server['max_players'] = int(stored_max)
        else:
            # DB'de kayıt yoksa env fallback, sonra DB'ye yaz
            env_max = cfg.get('CS2_MAXPLAYERS', 0)
            if env_max and int(env_max) > 0:
                server['max_players'] = int(env_max)
                set_state(db, 'max_players', str(env_max))

    except RCONError as exc:
        server['error'] = str(exc)
        _clear_online(db)

    return render_template(
        'dashboard.html',
        server=server,
        maps=_get_quick_maps(db),
        server_ip=cfg['SERVER_IP'],
        server_port=cfg['CS2_PORT'],
        active='home',
    )


@dashboard_bp.route('/set_password', methods=['POST'])
@login_required
def set_password():
    pw = request.form.get('password', '').strip()
    # Block shell-injection characters
    if pw and re.search(r'[;|&`$<>]', pw):
        flash(_('Invalid character in password.'), 'danger')
        return redirect(url_for('dashboard.index'))
    try:
        _rcon(f'sv_password "{pw}"')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Server Password', 'Removed' if not pw else 'Updated')
        flash(_('Server password updated.') if pw else _('Server password removed.'), 'success')
    except RCONError as exc:
        flash(_('Error: %(e)s', e=exc), 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/change_map', methods=['POST'])
@login_required
def change_map():
    map_name = request.form.get('map_name', '').strip()
    if not map_name or not re.match(r'^[a-zA-Z0-9_\-]+$', map_name):
        flash(_('Invalid map name.'), 'danger')
        return redirect(url_for('dashboard.index'))
    try:
        _rcon(f'changelevel {map_name}')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Map Changed', map_name)
        flash(_('Map changed \u2192 %(m)s', m=map_name), 'success')
    except RCONError as exc:
        flash(_('Error: %(e)s', e=exc), 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/player_action', methods=['POST'])
@login_required
def player_action():
    action = request.form.get('action', '')
    userid = request.form.get('userid', '').strip()
    reason = re.sub(r'["\';\\]', '', request.form.get('reason', 'Panel'))[:64]
    duration = request.form.get('duration', '60').strip()

    if not userid.isdigit():
        flash(_('Invalid player ID.'), 'danger')
        return redirect(url_for('dashboard.index'))
    if not duration.isdigit():
        duration = '60'

    try:
        if action == 'kick':
            _rcon(f'kickid {userid} "{reason}"')
            flash(_('Player kicked.'), 'success')
        elif action == 'ban':
            _rcon(f'banid {duration} {userid}')
            _rcon('writeid')
            flash(_('Player banned for %(d)s minutes.', d=duration), 'success')
        elif action == 'slay':
            _rcon(f'css_slay #{userid}')
            flash(_('Player slayed.'), 'success')
        else:
            flash(_('Unknown action.'), 'danger')
    except RCONError as exc:
        flash(_('RCON error: %(e)s', e=exc), 'danger')

    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/api/debug_rcon')
@login_required
def api_debug_rcon():
    """Geçici debug: raw RCON status çıktısını döner."""
    try:
        raw = _rcon('status')
        return {'raw': raw, 'lines': raw.splitlines()}, 200
    except Exception as exc:
        return {'error': str(exc)}, 500


@dashboard_bp.route('/api/status')
@login_required
def api_status():
    """AJAX — live status for the dashboard auto-refresh."""
    cfg = current_app.config
    db = cfg['DATABASE']
    try:
        raw = _rcon('status')
        parsed = parse_status(raw)
        # DB'den max_players oku
        stored_max = get_state(db, 'max_players', '')
        if stored_max and stored_max.isdigit() and int(stored_max) > 0:
            max_players = int(stored_max)
        else:
            env_max = cfg.get('CS2_MAXPLAYERS', 0)
            max_players = int(env_max) if env_max and int(env_max) > 0 else parsed['max_players']
        return jsonify({
            'online': True,
            'hostname': parsed['hostname'],
            'map': parsed['map'],
            'next_map': _get_next_map(parsed['map']),
            'player_count': parsed['player_count'],
            'max_players': max_players,
            'players': parsed['players'],
        })
    except RCONError as exc:
        return jsonify({'online': False, 'error': str(exc)})


@dashboard_bp.route('/api/metrics')
@login_required
def api_metrics():
    """Sunucu kaynak kullanımı: CPU, RAM, Disk."""
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()

    # CS2 data dizini (volume) için disk kullanımı
    cs2_path = current_app.config.get('CS2_DATA_PATH', '/')
    try:
        disk = psutil.disk_usage(cs2_path)
    except OSError:
        disk = psutil.disk_usage('/')

    # CS2 log dosyasının mtime → sunucu restart tespiti için
    log_mtime = 0
    logs_dir = os.path.join(cs2_path, 'game', 'csgo', 'logs')
    if os.path.isdir(logs_dir):
        try:
            log_files = [
                os.path.join(logs_dir, f)
                for f in os.listdir(logs_dir)
                if f.endswith('.log') and not f.startswith('.')
            ]
            if log_files:
                log_mtime = int(os.path.getmtime(max(log_files, key=os.path.getmtime)) * 1000)
        except OSError:
            pass

    return jsonify({
        'cpu_percent': round(cpu, 1),
        'ram_used_mb': round(mem.used / 1024 ** 2),
        'ram_total_mb': round(mem.total / 1024 ** 2),
        'ram_percent': round(mem.percent, 1),
        'disk_used_gb': round(disk.used / 1024 ** 3, 1),
        'disk_total_gb': round(disk.total / 1024 ** 3, 1),
        'disk_percent': round(disk.percent, 1),
        'log_mtime': log_mtime,
    })


@dashboard_bp.route('/api/console')
@login_required
def api_console():
    """Son N satır CS2 log çıktısı."""
    logs_dir = os.path.join(
        current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'logs'
    )
    lines: list[str] = []
    log_name = ''

    if os.path.isdir(logs_dir):
        try:
            log_files = [
                os.path.join(logs_dir, f)
                for f in os.listdir(logs_dir)
                if f.endswith('.log') and not f.startswith('.')
            ]
        except OSError:
            log_files = []

        if log_files:
            latest = max(log_files, key=os.path.getmtime)
            log_name = os.path.basename(latest)
            try:
                with open(latest, encoding='utf-8', errors='replace') as fh:
                    all_lines = fh.readlines()
                lines = [ln.rstrip('\n') for ln in all_lines[-150:]]
            except OSError:
                pass

    return jsonify({'lines': lines, 'file': log_name})


@dashboard_bp.route('/api/rcon', methods=['POST'])
@login_required
def api_rcon():
    """AJAX RCON terminal — kullanıcıdan gelen komutu CS2'ye iletir."""
    data = request.get_json(silent=True) or {}
    cmd = (data.get('cmd') or '').strip()
    if not cmd:
        return jsonify({'error': 'Komut boş'}), 400
    if len(cmd) > 256:
        return jsonify({'error': 'Komut çok uzun (maks 256 karakter)'}), 400
    try:
        output = _rcon(cmd)
        return jsonify({'output': output or '(Yanıt yok)'})
    except RCONError as exc:
        return jsonify({'error': str(exc)}), 502


@dashboard_bp.route('/api/restart_server', methods=['POST'])
@login_required
def api_restart_server():
    """Sunucuya RCON quit gönder — Docker restart policy yeniden başlatır."""
    try:
        _rcon('quit')
        return jsonify({'ok': True})
    except RCONError as exc:
        return jsonify({'error': str(exc)}), 502
