import os
import re
import shutil
import tarfile
import tempfile
import zipfile

from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, current_app, request, jsonify,
)
from flask_login import login_required, current_user
from flask_babel import _
from werkzeug.utils import secure_filename

from .models import log_action
plugins_bp = Blueprint('plugins', __name__, url_prefix='/plugins')

# Metamod system directories — never show/delete these
_SYSTEM_DIRS = {'metamod', 'metamod_x64', 'sourcemod'}

ALLOWED_UPLOAD_EXTS = {'.zip', '.tar.gz', '.so', '.vdf'}
MAX_UPLOAD_BYTES = 256 * 1024 * 1024  # 256 MB


# ── Helpers ────────────────────────────────────────────────────────────────────

def _addons_dir() -> str:
    return os.path.join(current_app.config['CS2_DATA_PATH'], 'game', 'csgo', 'addons')


def _safe_plugin_name(name: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', name))


def _css_plugins_dir() -> str:
    return os.path.join(_addons_dir(), 'counterstrikesharp', 'plugins')


def _find_plugin_path(name: str) -> tuple[str | None, bool]:
    """Return (actual_path, is_enabled) for a plugin, or (None, False).

    Searches both addons/ (legacy) and addons/counterstrikesharp/plugins/.
    """
    addons = _addons_dir()
    css_plugins = _css_plugins_dir()

    candidates = [
        (os.path.join(css_plugins, name), True),
        (os.path.join(css_plugins, f'{name}.disabled'), False),
        (os.path.join(addons, name), True),
        (os.path.join(addons, f'{name}.disabled'), False),
    ]
    for path, enabled in candidates:
        if os.path.isdir(path):
            return path, enabled
    return None, False


def _list_plugins() -> list[dict]:
    """Return info dicts for each user-installed plugin folder.

    Scans both addons/counterstrikesharp/plugins/ (primary) and addons/
    (legacy installs), deduplicating by plugin name.
    """
    addons = _addons_dir()
    css_plugins = _css_plugins_dir()

    plugins: list[dict] = []
    seen: set[str] = set()

    # CSS-native location first, then legacy addons/ root
    scan_dirs = [css_plugins, addons]

    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for entry in sorted(os.scandir(scan_dir), key=lambda e: e.name.lower()):
            if not entry.is_dir():
                continue
            folder = entry.name
            if folder.endswith('.disabled'):
                name = folder[:-9]
                enabled = False
            else:
                name = folder
                enabled = True

            if name in _SYSTEM_DIRS:
                continue
            if name.startswith('.'):
                continue
            if not _safe_plugin_name(name):
                continue
            if name in seen:
                continue
            # Skip addons/ entries that are CSS sub-dirs (counterstrikesharp etc)
            if scan_dir == addons and name in {'counterstrikesharp', 'sourcemod'}:
                continue
            seen.add(name)

            info = _plugin_info(name, entry.path, enabled)
            plugins.append(info)

    return sorted(plugins, key=lambda p: p['name'].lower())


def _plugin_info(name: str, path: str, enabled: bool = True) -> dict:
    """Gather metadata for a single plugin directory."""
    file_count = 0
    total_size = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            file_count += 1
            try:
                total_size += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass

    config_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.cfg', '.ini', '.txt', '.json', '.toml', '.yaml', '.yml'):
                rel = os.path.relpath(os.path.join(root, f), path)
                config_files.append(rel.replace('\\', '/'))

    # Check for a .md description file in the plugin root
    readme_file = None
    for fname in os.listdir(path):
        if fname.lower().endswith('.md') and os.path.isfile(os.path.join(path, fname)):
            readme_file = fname
            break

    return {
        'name': name,
        'path': path,
        'enabled': enabled,
        'file_count': file_count,
        'size_kb': round(total_size / 1024, 1),
        'config_files': config_files,
        'readme_file': readme_file,
    }


def _fix_permissions(path: str) -> None:
    """Recursively set dirs to 755 and files to 644."""
    for root, dirs, files in os.walk(path):
        os.chmod(root, 0o755)
        for f in files:
            try:
                os.chmod(os.path.join(root, f), 0o644)
            except OSError:
                pass


def _extract_to_tmp(src: str) -> tuple[str | None, str]:
    """Extract archive into a fresh temp directory. Returns (tmp_dir, error)."""
    tmp_dir = tempfile.mkdtemp()
    try:
        if src.endswith('.tar.gz') or src.endswith('.tgz'):
            with tarfile.open(src, 'r:gz') as tar:
                for m in tar.getmembers():
                    norm = os.path.normpath(m.name)
                    if norm.startswith('..') or os.path.isabs(norm):
                        continue
                    tar.extract(m, path=tmp_dir)
        else:
            with zipfile.ZipFile(src) as zf:
                for member in zf.namelist():
                    norm = os.path.normpath(member)
                    if norm.startswith('..') or os.path.isabs(norm):
                        continue
                    zf.extract(member, tmp_dir)
        return tmp_dir, ''
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None, str(e)


def _install_from_tmp(tmp_dir: str, addons_dir: str, plugin_name: str) -> str:
    """Copy extracted files to the correct addons paths.

    If the archive contains an ``addons/counterstrikesharp/`` tree (the
    standard GoldKingZ / CSS plugin release layout), the relevant sub-trees
    are merged directly into the live ``counterstrikesharp/`` directory so
    nothing ends up one level too deep.

    Otherwise the whole extracted tree is placed under
    ``addons/<plugin_name>/`` as before.

    Returns the final plugin directory path.
    """
    css_root_in_tmp = os.path.join(tmp_dir, 'addons', 'counterstrikesharp')

    if os.path.isdir(css_root_in_tmp):
        # Merge each sub-folder (plugins/, shared/, configs/, …) into the
        # real counterstrikesharp directory.
        css_dest = os.path.join(addons_dir, 'counterstrikesharp')
        for sub in os.listdir(css_root_in_tmp):
            src_sub = os.path.join(css_root_in_tmp, sub)
            dst_sub = os.path.join(css_dest, sub)
            if os.path.isdir(src_sub):
                for item in os.listdir(src_sub):
                    s = os.path.join(src_sub, item)
                    d = os.path.join(dst_sub, item)
                    if os.path.exists(d):
                        shutil.rmtree(d) if os.path.isdir(d) else os.remove(d)
                    os.makedirs(dst_sub, exist_ok=True)
                    shutil.copytree(s, d) if os.path.isdir(s) else shutil.copy2(s, d)
        plugin_dir = os.path.join(css_dest, 'plugins', plugin_name)
    else:
        # Simple layout — put contents under counterstrikesharp/plugins/<plugin_name>/
        # If the archive has exactly one top-level folder, unwrap it.
        entries = [e for e in os.listdir(tmp_dir) if not e.startswith('.')]
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            src_root = os.path.join(tmp_dir, entries[0])
        else:
            src_root = tmp_dir

        plugin_dir = os.path.join(addons_dir, 'counterstrikesharp', 'plugins', plugin_name)
        if os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        shutil.copytree(src_root, plugin_dir)

    return plugin_dir


def _extract_archive(src: str, dest_dir: str) -> tuple[bool, str]:
    """Extract zip or tar.gz into dest_dir safely (legacy helper)."""
    os.makedirs(dest_dir, exist_ok=True)
    try:
        if src.endswith('.tar.gz') or src.endswith('.tgz'):
            with tarfile.open(src, 'r:gz') as tar:
                for m in tar.getmembers():
                    norm = os.path.normpath(m.name)
                    if norm.startswith('..') or os.path.isabs(norm):
                        continue
                    tar.extract(m, path=dest_dir)
        else:
            with zipfile.ZipFile(src) as zf:
                for member in zf.namelist():
                    norm = os.path.normpath(member)
                    if norm.startswith('..') or os.path.isabs(norm):
                        continue
                    zf.extract(member, dest_dir)
        return True, ''
    except Exception as e:
        return False, str(e)


# ── Routes ─────────────────────────────────────────────────────────────────────

@plugins_bp.route('/')
@login_required
def index():
    metamod_installed = os.path.isdir(
        os.path.join(_addons_dir(), 'metamod')
    )
    return render_template(
        'plugins.html',
        plugins=_list_plugins(),
        metamod_installed=metamod_installed,
        active='plugins',
    )


@plugins_bp.route('/readme/<plugin_name>')
@login_required
def readme(plugin_name: str):
    if not _safe_plugin_name(plugin_name):
        return jsonify({'error': 'Geçersiz eklenti adı'}), 400

    path, _ = _find_plugin_path(plugin_name)
    if path is None:
        return jsonify({'error': 'Eklenti bulunamadı'}), 404

    md_path = None
    for fname in os.listdir(path):
        if fname.lower().endswith('.md') and os.path.isfile(os.path.join(path, fname)):
            md_path = os.path.join(path, fname)
            break

    if md_path is None:
        return jsonify({'error': 'Açıklama dosyası yok'}), 404

    real_path = os.path.realpath(md_path)
    real_plugin = os.path.realpath(path)
    if not real_path.startswith(real_plugin + os.sep):
        return jsonify({'error': 'Güvenlik hatası'}), 403

    try:
        with open(md_path, encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@plugins_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    f = request.files.get('plugin_file')
    if not f or not f.filename:
        flash(_('No file selected.'), 'danger')
        return redirect(url_for('plugins.index'))

    filename = secure_filename(f.filename)
    # Accept .zip, .tar.gz, standalone .so or .vdf
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in ALLOWED_UPLOAD_EXTS):
        flash(_('Unsupported file type. (.zip, .tar.gz, .so, .vdf)'), 'danger')
        return redirect(url_for('plugins.index'))

    plugin_name = request.form.get('plugin_name', '').strip()
    if not plugin_name:
        # Derive from filename
        plugin_name = filename.split('.')[0]
    plugin_name = secure_filename(plugin_name)

    if not _safe_plugin_name(plugin_name):
        flash(_('Invalid plugin name. (use letters, numbers, _ and -)'), 'danger')
        return redirect(url_for('plugins.index'))

    if plugin_name in _SYSTEM_DIRS:
        flash(_('This name is reserved by the system.'), 'danger')
        return redirect(url_for('plugins.index'))

    dest = os.path.join(_addons_dir(), plugin_name)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp:
            tmp_path = tmp.name
        f.save(tmp_path)

        if lower.endswith('.zip') or lower.endswith('.tar.gz') or lower.endswith('.tgz'):
            tmp_extract, err = _extract_to_tmp(tmp_path)
            if tmp_extract is None:
                flash(_('Archive extraction error: %(e)s', e=err), 'danger')
                return redirect(url_for('plugins.index'))
            try:
                plugin_dir = _install_from_tmp(tmp_extract, _addons_dir(), plugin_name)
                _fix_permissions(plugin_dir)
            finally:
                shutil.rmtree(tmp_extract, ignore_errors=True)
        else:
            # Single .so or .vdf — place directly in plugin dir
            os.makedirs(dest, exist_ok=True)
            dst_file = os.path.join(dest, filename)
            if not os.path.realpath(dst_file).startswith(os.path.realpath(dest)):
                flash(_('Security error.'), 'danger')
                return redirect(url_for('plugins.index'))
            shutil.copy2(tmp_path, dst_file)
            _fix_permissions(dest)

        flash(_('Plugin "%(n)s" uploaded.', n=plugin_name), 'success')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Plugin Uploaded', plugin_name)
    except Exception as e:
        flash(_('Upload error: %(e)s', e=e), 'danger')
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return redirect(url_for('plugins.index'))


@plugins_bp.route('/toggle/<plugin_name>', methods=['POST'])
@login_required
def toggle(plugin_name: str):
    if not _safe_plugin_name(plugin_name):
        flash(_('Invalid plugin name.'), 'danger')
        return redirect(url_for('plugins.index'))

    if plugin_name in _SYSTEM_DIRS:
        flash(_('System plugin cannot be modified.'), 'danger')
        return redirect(url_for('plugins.index'))

    path, enabled = _find_plugin_path(plugin_name)
    if path is None:
        flash(_('Plugin not found.'), 'warning')
        return redirect(url_for('plugins.index'))

    addons = _addons_dir()
    real_addons = os.path.realpath(addons)

    if enabled:
        new_path = os.path.join(addons, f'{plugin_name}.disabled')
        action_msg = _('"%(n)s" disabled.', n=plugin_name)
    else:
        new_path = os.path.join(addons, plugin_name)
        action_msg = _('"%(n)s" enabled.', n=plugin_name)

    if not os.path.realpath(new_path).startswith(real_addons + os.sep):
        flash(_('Security error.'), 'danger')
        return redirect(url_for('plugins.index'))

    try:
        os.rename(path, new_path)
        flash(action_msg, 'success')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Plugin Status Changed',
                   f'{plugin_name} \u2192 {"enabled" if not enabled else "disabled"}')
    except Exception as e:
        flash(_('Status change error: %(e)s', e=e), 'danger')

    return redirect(url_for('plugins.index'))


@plugins_bp.route('/delete/<plugin_name>', methods=['POST'])
@login_required
def delete(plugin_name: str):
    if not _safe_plugin_name(plugin_name):
        flash(_('Invalid plugin name.'), 'danger')
        return redirect(url_for('plugins.index'))

    if plugin_name in _SYSTEM_DIRS:
        flash(_('System plugin cannot be deleted.'), 'danger')
        return redirect(url_for('plugins.index'))

    path, _ = _find_plugin_path(plugin_name)
    if path is None:
        flash(_('Plugin not found.'), 'warning')
        return redirect(url_for('plugins.index'))

    real_path = os.path.realpath(path)
    real_addons = os.path.realpath(_addons_dir())

    if not real_path.startswith(real_addons + os.sep):
        flash(_('Security error: invalid path.'), 'danger')
        return redirect(url_for('plugins.index'))

    try:
        shutil.rmtree(path)
        flash(_('"%(n)s" deleted.', n=plugin_name), 'success')
        log_action(current_app.config['DATABASE'], current_user.username,
                   'Plugin Deleted', plugin_name)
    except Exception as e:
        flash(_('Delete error: %(e)s', e=e), 'danger')

    return redirect(url_for('plugins.index'))


@plugins_bp.route('/edit/<plugin_name>')
@login_required
def edit(plugin_name: str):
    if not _safe_plugin_name(plugin_name):
        flash(_('Invalid plugin name.'), 'danger')
        return redirect(url_for('plugins.index'))

    path, enabled = _find_plugin_path(plugin_name)
    if path is None:
        flash(_('Plugin not found.'), 'warning')
        return redirect(url_for('plugins.index'))

    info = _plugin_info(plugin_name, path, enabled)

    # Which config file to show?
    cfg_file = request.args.get('file')
    content = None
    current_file = None

    if cfg_file:
        # Sanitize: resolve within plugin dir only
        safe = os.path.normpath(os.path.join(path, cfg_file))
        if not safe.startswith(os.path.realpath(path)):
            flash(_('Invalid file path.'), 'danger')
            return redirect(url_for('plugins.edit', plugin_name=plugin_name))
        if os.path.isfile(safe):
            try:
                with open(safe, encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                current_file = cfg_file
            except Exception as e:
                flash(_('Could not read file: %(e)s', e=e), 'danger')
    elif info['config_files']:
        # Default to first config file
        return redirect(url_for(
            'plugins.edit',
            plugin_name=plugin_name,
            file=info['config_files'][0],
        ))

    return render_template(
        'plugin_edit.html',
        plugin=info,
        content=content,
        current_file=current_file,
        active='plugins',
    )


@plugins_bp.route('/edit/<plugin_name>/save', methods=['POST'])
@login_required
def save_config(plugin_name: str):
    if not _safe_plugin_name(plugin_name):
        return jsonify(ok=False, msg='Geçersiz eklenti adı'), 400

    cfg_file = request.form.get('file', '')
    content = request.form.get('content', '')

    if not cfg_file:
        return jsonify(ok=False, msg='Dosya belirtilmedi'), 400

    path, _ = _find_plugin_path(plugin_name)
    if path is None:
        return jsonify(ok=False, msg='Eklenti bulunamadı'), 404

    safe = os.path.normpath(os.path.join(path, cfg_file))
    if not os.path.realpath(safe).startswith(os.path.realpath(path)):
        return jsonify(ok=False, msg='Güvenlik hatası'), 403

    try:
        with open(safe, 'w', encoding='utf-8') as fh:
            fh.write(content)
        return jsonify(ok=True, msg='Kaydedildi')
    except Exception as e:
        return jsonify(ok=False, msg=str(e)), 500
