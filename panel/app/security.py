"""Shared security helpers: role-based access control and safe redirects."""
import os
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, request
from flask_login import current_user

# Ordered from least to most privileged. Each role includes the rights of the
# roles before it.
#   viewer   - read-only access to dashboards, lists and logs
#   operator - day-to-day server control (map, players, hostname, game mode)
#   admin    - everything, including RCON console, file uploads, plugin and
#              config editing, in-game admin management and panel users
ROLES = ('viewer', 'operator', 'admin')
_ROLE_LEVEL = {name: level for level, name in enumerate(ROLES)}


def role_level(role: str) -> int:
    """Privilege level of a role. Unknown roles get no privileges."""
    return _ROLE_LEVEL.get(role, -1)


def has_role(user, required: str) -> bool:
    """True if ``user`` is authenticated and holds ``required`` or higher."""
    if required not in _ROLE_LEVEL:
        raise ValueError(f'Unknown role: {required!r}')
    if not getattr(user, 'is_authenticated', False):
        return False
    return role_level(getattr(user, 'role', None)) >= _ROLE_LEVEL[required]


def role_required(required: str):
    """Route decorator: abort with 403 unless the current user has ``required``.

    Must be placed *below* ``@login_required`` so anonymous users are sent to
    the login page instead of receiving a 403.
    """
    if required not in _ROLE_LEVEL:
        raise ValueError(f'Unknown role: {required!r}')

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not has_role(current_user, required):
                abort(403)
            return view(*args, **kwargs)
        # Marker used by the test-suite to assert every route is role-gated.
        # functools.wraps copies __dict__, so it survives outer decorators.
        wrapped.required_role = required
        return wrapped
    return decorator


def is_safe_redirect_url(target) -> bool:
    """Allow only relative, same-site paths such as ``/maps/``.

    Rejects absolute URLs, scheme-relative URLs (``//evil.com``), backslash
    tricks (``/\\evil.com``) and anything with a scheme or host.
    """
    if not target or not isinstance(target, str):
        return False
    if any(c in target for c in ('\\', '\r', '\n', '\t')):
        return False
    if not target.startswith('/') or target.startswith('//'):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc


def safe_redirect_target(target, fallback: str) -> str:
    """Return ``target`` if it is a safe local path, otherwise ``fallback``."""
    return target if is_safe_redirect_url(target) else fallback


def wants_json() -> bool:
    """Heuristic: should an error response for this request be JSON?"""
    if request.path.startswith('/api/') or '/api/' in request.path:
        return True
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    return best == 'application/json' and \
        request.accept_mimetypes[best] > request.accept_mimetypes['text/html']


def is_within_directory(base: str, target: str) -> bool:
    """True if ``target`` resolves to ``base`` itself or a path inside it.

    Both paths are resolved with ``realpath`` (following symlinks) and compared
    with ``commonpath``, so sibling directories that merely share a prefix
    (``/plugins/Foo`` vs ``/plugins/Foo2``) are correctly rejected.
    """
    base_real = os.path.realpath(base)
    target_real = os.path.realpath(target)
    try:
        return os.path.commonpath([base_real, target_real]) == base_real
    except ValueError:  # different drives on Windows
        return False
