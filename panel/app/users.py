from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app,
)
from flask_login import login_required, current_user
from flask_babel import _
from .models import get_all_users, create_user, delete_user, update_password, get_user_by_username, log_action

users_bp = Blueprint('users', __name__, url_prefix='/users')


@users_bp.route('/')
@login_required
def index():
    users = get_all_users(current_app.config['DATABASE'])
    return render_template(
        'users.html',
        users=users,
        server_ip=current_app.config['SERVER_IP'],
        server_port=current_app.config['CS2_PORT'],
        active='users',
    )


@users_bp.route('/create', methods=['POST'])
@login_required
def create():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    password2 = request.form.get('password2', '')

    if not username or not password:
        flash(_('Username and password are required.'), 'danger')
        return redirect(url_for('users.index'))
    if len(username) > 32 or not username.replace('_', '').replace('-', '').isalnum():
        flash(_('Username may only contain letters, numbers, _ and - (max 32 chars).'), 'danger')
        return redirect(url_for('users.index'))
    if password != password2:
        flash(_('Passwords do not match.'), 'danger')
        return redirect(url_for('users.index'))
    if len(password) < 6:
        flash(_('Password must be at least 6 characters.'), 'danger')
        return redirect(url_for('users.index'))
    if get_user_by_username(current_app.config['DATABASE'], username):
        flash(_('This username is already taken.'), 'danger')
        return redirect(url_for('users.index'))

    create_user(current_app.config['DATABASE'], username, password)
    log_action(current_app.config['DATABASE'], current_user.username,
               'User Created', username)
    flash(_('User "%(u)s" created.', u=username), 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
def delete(user_id):
    if user_id == current_user.id:
        flash(_('You cannot delete your own account.'), 'danger')
        return redirect(url_for('users.index'))
    delete_user(current_app.config['DATABASE'], user_id)
    log_action(current_app.config['DATABASE'], current_user.username,
               'User Deleted', f'ID: {user_id}')
    flash(_('User deleted.'), 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/change_password/<int:user_id>', methods=['POST'])
@login_required
def change_password(user_id):
    new_pw = request.form.get('new_password', '')
    if len(new_pw) < 6:
        flash(_('New password must be at least 6 characters.'), 'danger')
        return redirect(url_for('users.index'))
    update_password(current_app.config['DATABASE'], user_id, new_pw)
    log_action(current_app.config['DATABASE'], current_user.username,
               'Password Changed', f'ID: {user_id}')
    flash(_('Password updated.'), 'success')
    return redirect(url_for('users.index'))
