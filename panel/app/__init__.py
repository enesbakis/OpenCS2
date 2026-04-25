import os
from flask import Flask, session, redirect, url_for, request
from flask_login import LoginManager
from flask_babel import Babel, lazy_gettext as _l
from .config import Config

login_manager = LoginManager()
babel = Babel()


def get_locale():
    cfg = Config()
    lang = session.get('lang')
    if lang and lang in cfg.SUPPORTED_LANGUAGES:
        return lang
    return request.accept_languages.best_match(cfg.SUPPORTED_LANGUAGES.keys(), default='en')


def create_app():
    app = Flask(__name__)
    cfg = Config()
    app.config.from_object(cfg)
    app.config['LANGUAGES'] = cfg.SUPPORTED_LANGUAGES

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = _l('Please log in to access this page.')
    login_manager.login_message_category = 'warning'

    babel.init_app(app, locale_selector=get_locale)

    with app.app_context():
        from .models import init_db, get_or_create_admin
        init_db(app.config['DATABASE'])
        get_or_create_admin(
            app.config['DATABASE'],
            os.environ.get('PANEL_ADMIN_USER', 'admin'),
            os.environ.get('PANEL_ADMIN_PASS', 'changeme'),
        )

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
    def load_user(user_id):
        from .models import get_user_by_id
        return get_user_by_id(app.config['DATABASE'], int(user_id))

    @app.route('/set_language/<lang>')
    def set_language(lang):
        if lang in cfg.SUPPORTED_LANGUAGES:
            session['lang'] = lang
        next_url = request.args.get('next') or url_for('dashboard.index')
        return redirect(next_url)

    @app.context_processor
    def inject_locale():
        return {
            'get_locale': get_locale,
            'supported_languages': cfg.SUPPORTED_LANGUAGES,
        }

    @app.errorhandler(404)
    def page_not_found(e):
        return redirect(url_for('dashboard.index'))

    @app.route('/health')
    def health():
        return {'status': 'ok'}, 200

    return app
