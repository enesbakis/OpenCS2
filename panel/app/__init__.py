import logging
import os
import secrets

from flask import Flask, session, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager
from flask_babel import Babel, lazy_gettext as _l, gettext as _
from flask_wtf.csrf import CSRFProtect, CSRFError
from .config import Config, INSECURE_SECRET_KEYS
from .security import has_role, safe_redirect_target, wants_json

login_manager = LoginManager()
babel = Babel()
csrf = CSRFProtect()
log = logging.getLogger(__name__)


def get_locale():
    cfg = Config()
    lang = session.get('lang')
    if lang and lang in cfg.SUPPORTED_LANGUAGES:
        return lang
    return request.accept_languages.best_match(cfg.SUPPORTED_LANGUAGES.keys(), default='en')


def _check_secret_key(app: Flask) -> None:
    """Refuse to run with a missing or well-known SECRET_KEY.

    Anyone who knows the key can forge session cookies and log in as any user,
    so a placeholder value is never acceptable outside of tests.
    """
    key = app.config.get('SECRET_KEY') or ''
    if app.testing:
        return
    if key in INSECURE_SECRET_KEYS or len(key) < 16:
        raise RuntimeError(
            'SECRET_KEY is missing, too short or a known placeholder. '
            'Set SECRET_KEY to a long random value, for example the output of: '
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )


def _bootstrap_admin(app: Flask) -> None:
    """Create the initial admin account on first start.

    If PANEL_ADMIN_PASS is not set, a random password is generated and written
    to the log once, so no fixed default password ever exists.
    """
    from .models import get_or_create_admin

    username = os.environ.get('PANEL_ADMIN_USER') or 'admin'
    password = os.environ.get('PANEL_ADMIN_PASS') or ''
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True

    created = get_or_create_admin(app.config['DATABASE'], username, password)
    if not created:
        return
    if generated:
        app.logger.warning(
            'Created initial admin user "%s" with generated password: %s  '
            '(shown only once; change it after logging in)', username, password,
        )
    elif password == 'changeme':
        app.logger.warning(
            'Initial admin user "%s" uses the insecure default password "changeme". '
            'Change it immediately.', username,
        )


def create_app(test_config: dict | None = None):
    app = Flask(__name__)
    cfg = Config()
    app.config.from_object(cfg)
    app.config['LANGUAGES'] = cfg.SUPPORTED_LANGUAGES
    if test_config:
        app.config.update(test_config)

    if not app.logger.handlers or app.logger.level == logging.NOTSET:
        app.logger.setLevel(logging.INFO)

    _check_secret_key(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = _l('Please log in to access this page.')
    login_manager.login_message_category = 'warning'

    csrf.init_app(app)
    babel.init_app(app, locale_selector=get_locale)

    with app.app_context():
        from .models import init_db
        init_db(app.config['DATABASE'])
        _bootstrap_admin(app)

    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .maps import maps_bp
    from .metamod import metamod_bp
    from .counterstrikesharp import css_bp
    from .plugins import plugins_bp
    from .server import server_bp
    from .users import users_bp
    from .csadmins import csadmins_bp
    from .audit import audit_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(maps_bp)
    app.register_blueprint(metamod_bp)
    app.register_blueprint(css_bp)
    app.register_blueprint(plugins_bp)
    app.register_blueprint(server_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(csadmins_bp)
    app.register_blueprint(audit_bp)

    @login_manager.user_loader
    def load_user(session_id):
        from .models import load_user_from_session_id
        return load_user_from_session_id(app.config['DATABASE'], session_id)

    @app.route('/set_language/<lang>')
    def set_language(lang):
        if lang in cfg.SUPPORTED_LANGUAGES:
            session['lang'] = lang
        next_url = safe_redirect_target(request.args.get('next'), url_for('dashboard.index'))
        return redirect(next_url)

    @app.context_processor
    def inject_globals():
        return {
            'get_locale': get_locale,
            'supported_languages': cfg.SUPPORTED_LANGUAGES,
            'has_role': has_role,
        }

    def _back(fallback_endpoint='dashboard.index'):
        return redirect(safe_redirect_target(
            _same_site_referrer(), url_for(fallback_endpoint)))

    def _same_site_referrer():
        ref = request.referrer or ''
        host_prefix = request.host_url  # e.g. http://panel:5000/
        if ref.startswith(host_prefix):
            return '/' + ref[len(host_prefix):]
        return None

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        log.warning('CSRF validation failed for %s %s: %s', request.method, request.path, e.description)
        if wants_json():
            return jsonify(ok=False, error='CSRF token missing or invalid. Reload the page.'), 400
        flash(_('Your session form has expired. Please try again.'), 'warning')
        return _back()

    @app.errorhandler(403)
    def forbidden(e):
        if wants_json():
            return jsonify(ok=False, error='Forbidden: insufficient role.'), 403
        if request.method == 'GET' and request.endpoint == 'dashboard.index':
            # Nowhere left to send the user (e.g. an account with no valid role).
            return _('You do not have permission to view this panel.'), 403
        flash(_('You do not have permission to do that.'), 'danger')
        if request.method == 'GET':
            return redirect(url_for('dashboard.index'))
        return _back()

    @app.errorhandler(413)
    def too_large(e):
        limit_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        if wants_json():
            return jsonify(ok=False, error=f'Upload too large (max {limit_mb} MB).'), 413
        flash(_('Upload too large (max %(mb)s MB).', mb=limit_mb), 'danger')
        return _back()

    @app.errorhandler(404)
    def page_not_found(e):
        return redirect(url_for('dashboard.index'))

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp

    @app.route('/health')
    def health():
        return {'status': 'ok'}, 200

    return app
