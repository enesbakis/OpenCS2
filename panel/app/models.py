import hashlib
import hmac
import os
import sqlite3
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .security import ROLES, has_role


class LastAdminError(Exception):
    """Raised when an operation would leave the panel without any admin."""


class User(UserMixin):
    def __init__(self, id: int, username: str, password_hash: str, role: str = 'admin'):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_role(self, required: str) -> bool:
        return has_role(self, required)

    @property
    def password_fingerprint(self) -> str:
        return hashlib.sha256(self.password_hash.encode()).hexdigest()[:16]

    def get_id(self) -> str:
        # Embedding a fingerprint of the password hash in the session id means
        # that changing a password invalidates every existing session and
        # "remember me" cookie for that user.
        return f'{self.id}:{self.password_fingerprint}'


def _row_to_user(row):
    return User(row['id'], row['username'], row['password_hash'], row['role']) if row else None


def _get_db(database_path: str):
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(database_path: str) -> None:
    with _get_db(database_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'admin'
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS server_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT    NOT NULL,
                action     TEXT    NOT NULL,
                detail     TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now'))
            )
        ''')
        conn.commit()


def get_or_create_admin(database_path: str, username: str, password: str) -> bool:
    """Create the bootstrap admin only when the panel has no users at all.

    Returns True if a user was created. Once any account exists this is a
    no-op, so deleting or renaming the bootstrap admin is respected and a
    leaked PANEL_ADMIN_PASS cannot re-create it on the next restart.
    """
    password_hash = generate_password_hash(password)
    with _get_db(database_path) as conn:
        # Several gunicorn workers run this at the same time on first start.
        # BEGIN IMMEDIATE takes the write lock before the check, so exactly one
        # worker creates the account and the others see it and return False.
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            conn.rollback()
            return False
        try:
            conn.execute(
                'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                (username, password_hash, 'admin'),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
        conn.commit()
        return True


def get_user_by_id(database_path: str, user_id: int):
    with _get_db(database_path) as conn:
        row = conn.execute(
            'SELECT id, username, password_hash, role FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
    return _row_to_user(row)


def load_user_from_session_id(database_path: str, session_id: str):
    """Resolve a Flask-Login session id of the form ``<id>:<fingerprint>``.

    Returns None (forcing re-login) for malformed ids, unknown users, or when
    the password has changed since the session was created.
    """
    user_part, sep, fingerprint = (session_id or '').partition(':')
    if not sep or not user_part.isdecimal():
        return None
    user = get_user_by_id(database_path, int(user_part))
    if user is None or not hmac.compare_digest(user.password_fingerprint, fingerprint):
        return None
    return user


def get_user_by_username(database_path: str, username: str):
    with _get_db(database_path) as conn:
        row = conn.execute(
            'SELECT id, username, password_hash, role FROM users WHERE username = ?',
            (username,),
        ).fetchone()
    return _row_to_user(row)


def get_all_users(database_path: str):
    with _get_db(database_path) as conn:
        rows = conn.execute(
            'SELECT id, username, password_hash, role FROM users ORDER BY id'
        ).fetchall()
    return [_row_to_user(r) for r in rows]


def create_user(database_path: str, username: str, password: str, role: str = 'viewer') -> None:
    if role not in ROLES:
        raise ValueError(f'Unknown role: {role!r}')
    with _get_db(database_path) as conn:
        conn.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), role),
        )
        conn.commit()


def _other_admin_exists(conn, user_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM users WHERE role = 'admin' AND id != ? LIMIT 1", (user_id,),
    ).fetchone() is not None


def delete_user(database_path: str, user_id: int) -> None:
    """Delete a user. Raises LastAdminError if it is the only remaining admin."""
    with _get_db(database_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
        if row and row['role'] == 'admin' and not _other_admin_exists(conn, user_id):
            conn.rollback()
            raise LastAdminError()
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()


def update_role(database_path: str, user_id: int, role: str) -> None:
    """Change a user's role. Raises LastAdminError when demoting the last admin."""
    if role not in ROLES:
        raise ValueError(f'Unknown role: {role!r}')
    with _get_db(database_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
        if row and row['role'] == 'admin' and role != 'admin' and not _other_admin_exists(conn, user_id):
            conn.rollback()
            raise LastAdminError()
        conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
        conn.commit()


def update_password(database_path: str, user_id: int, new_password: str) -> None:
    with _get_db(database_path) as conn:
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), user_id),
        )
        conn.commit()


def get_state(database_path: str, key: str, default: str = '') -> str:
    with _get_db(database_path) as conn:
        row = conn.execute(
            'SELECT value FROM server_state WHERE key = ?', (key,)
        ).fetchone()
    return row['value'] if row else default


def set_state(database_path: str, key: str, value: str) -> None:
    with _get_db(database_path) as conn:
        conn.execute(
            'INSERT INTO server_state (key, value) VALUES (?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value),
        )
        conn.commit()


def log_action(database_path: str, username: str, action: str, detail: str = '') -> None:
    with _get_db(database_path) as conn:
        conn.execute(
            'INSERT INTO audit_log (username, action, detail) VALUES (?, ?, ?)',
            (username, action, detail),
        )
        conn.commit()


def get_audit_logs(database_path: str, limit: int = 500) -> list:
    with _get_db(database_path) as conn:
        rows = conn.execute(
            'SELECT id, username, action, detail, created_at '
            'FROM audit_log ORDER BY id DESC LIMIT ?',
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
