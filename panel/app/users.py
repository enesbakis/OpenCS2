from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app, abort,
)
from flask_login import login_required, current_user, login_user
from flask_babel import _
from .models import (
    get_all_users, get_user_by_id, create_user, delete_user, update_password,
    update_role, get_user_by_username, log_action, LastAdminError,
)
from .security import ROLES, role_required

users_bp = Blueprint('users', __name__, url_prefix='/users')

MIN_PASSWORD_LENGTH = 8


def _db():
    return current_app.config['DATABASE']


@users_bp.route('/')
@login_required
def index():
    # Non-admins only see their own account (to change their password).
    if current_user.has_role('admin'):
        users = get_all_users(_db())
    else:
        users = [current_user]
    return render_template(
        'users.html',
        users=users,
        roles=ROLES,
        min_password_length=MIN_PASSWORD_LENGTH,
        server_ip=current_app.config['SERVER_IP'],
        server_port=current_app.config['CS2_PORT'],
        active='users',
    )


@users_bp.route('/create', methods=['POST'])
@login_required
@role_required('admin')
def create():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    password2 = request.form.get('password2', password)
    role = request.form.get('role', 'viewer')

    if not username or not password:
        flash(_('Username and password are required.'), 'danger')
        return redirect(url_for('users.index'))
    if len(username) > 32 or not username.replace('_', '').replace('-', '').isalnum():
        flash(_('Username may only contain letters, numbers, _ and - (max 32 chars).'), 'danger')
        return redirect(url_for('users.index'))
    if password != password2:
        flash(_('Passwords do not match.'), 'danger')
        return redirect(url_for('users.index'))
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(_('Password must be at least %(n)s characters.', n=MIN_PASSWORD_LENGTH), 'danger')
        return redirect(url_for('users.index'))
    if role not in ROLES:
        flash(_('Invalid role.'), 'danger')
        return redirect(url_for('users.index'))
    if get_user_by_username(_db(), username):
        flash(_('This username is already taken.'), 'danger')
        return redirect(url_for('users.index'))

    create_user(_db(), username, password, role)
    log_action(_db(), current_user.username, 'User Created', f'{username} ({role})')
    flash(_('User "%(u)s" created.', u=username), 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete(user_id):
    if user_id == current_user.id:
        flash(_('You cannot delete your own account.'), 'danger')
        return redirect(url_for('users.index'))
    target = get_user_by_id(_db(), user_id)
    if target is None:
        abort(404)
    try:
        delete_user(_db(), user_id)
    except LastAdminError:
        flash(_('You cannot delete the last admin.'), 'danger')
        return redirect(url_for('users.index'))
    log_action(_db(), current_user.username, 'User Deleted', target.username)
    flash(_('User deleted.'), 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/role/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def change_role(user_id):
    role = request.form.get('role', '')
    if role not in ROLES:
        flash(_('Invalid role.'), 'danger')
        return redirect(url_for('users.index'))
    target = get_user_by_id(_db(), user_id)
    if target is None:
        abort(404)
    try:
        update_role(_db(), user_id, role)
    except LastAdminError:
        flash(_('You cannot remove the admin role from the last admin.'), 'danger')
        return redirect(url_for('users.index'))
    log_action(_db(), current_user.username, 'Role Changed', f'{target.username}: {target.role} -> {role}')
    flash(_('Role updated.'), 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/change_password/<int:user_id>', methods=['POST'])
@login_required
def change_password(user_id):
    is_self = user_id == current_user.id
    # Users may change their own password; only admins may reset others'.
    if not is_self and not current_user.has_role('admin'):
        abort(403)

    target = get_user_by_id(_db(), user_id)
    if target is None:
        abort(404)

    new_pw = request.form.get('new_password', '')
    if is_self:
        # Re-authenticate so a hijacked session cannot lock the owner out.
        if not target.check_password(request.form.get('current_password', '')):
            flash(_('Current password is incorrect.'), 'danger')
            return redirect(url_for('users.index'))
    if len(new_pw) < MIN_PASSWORD_LENGTH:
        flash(_('New password must be at least %(n)s characters.', n=MIN_PASSWORD_LENGTH), 'danger')
        return redirect(url_for('users.index'))

    update_password(_db(), user_id, new_pw)
    log_action(_db(), current_user.username, 'Password Changed', target.username)
    if is_self:
        # The session id embeds a password fingerprint; refresh it so the
        # current session stays valid while all other sessions are revoked.
        login_user(get_user_by_id(_db(), user_id), remember=True)
    flash(_('Password updated.'), 'success')
    return redirect(url_for('users.index'))
