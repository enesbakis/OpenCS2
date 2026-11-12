from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from .models import get_user_by_username, log_action
from .security import safe_redirect_target

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash(_('Username and password are required.'), 'danger')
            return render_template('login.html')

        user = get_user_by_username(current_app.config['DATABASE'], username)
        if user and user.check_password(password):
            login_user(user, remember=True)
            log_action(current_app.config['DATABASE'], user.username, 'Login', request.remote_addr or '')
            next_page = safe_redirect_target(request.args.get('next'), url_for('dashboard.index'))
            return redirect(next_page)

        current_app.logger.warning('Failed login for user %r from %s', username[:64], request.remote_addr)
        flash(_('Invalid username or password.'), 'danger')

    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash(_('Logged out.'), 'info')
    return redirect(url_for('auth.login'))
