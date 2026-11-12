from flask import Blueprint, render_template, current_app
from flask_login import login_required

from .models import get_audit_logs
from .security import role_required

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')


@audit_bp.route('/')
@login_required
@role_required('admin')
def index():
    logs = get_audit_logs(current_app.config['DATABASE'])
    return render_template('audit.html', logs=logs, active='audit')
