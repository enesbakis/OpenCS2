import os
import sqlite3
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin):
    def __init__(self, id: int, username: str, password_hash: str, role: str = 'admin'):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


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


def get_or_create_admin(database_path: str, username: str, password: str) -> None:
    with _get_db(database_path) as conn:
        try:
            conn.execute(
                'INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                (username, generate_password_hash(password), 'admin'),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # User already exists — normal flow


def get_user_by_id(database_path: str, user_id: int):
    with _get_db(database_path) as conn:
        row = conn.execute(
            'SELECT id, username, password_hash, role FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
    return User(row['id'], row['username'], row['password_hash'], row['role']) if row else None


def get_user_by_username(database_path: str, username: str):
    with _get_db(database_path) as conn:
        row = conn.execute(
            'SELECT id, username, password_hash, role FROM users WHERE username = ?',
            (username,),
        ).fetchone()
    return User(row['id'], row['username'], row['password_hash'], row['role']) if row else None


def get_all_users(database_path: str):
    with _get_db(database_path) as conn:
        rows = conn.execute(
            'SELECT id, username, password_hash, role FROM users'
        ).fetchall()
    return [User(r['id'], r['username'], r['password_hash'], r['role']) for r in rows]


def create_user(database_path: str, username: str, password: str, role: str = 'admin') -> None:
    with _get_db(database_path) as conn:
        conn.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), role),
        )
        conn.commit()


def delete_user(database_path: str, user_id: int) -> None:
    with _get_db(database_path) as conn:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
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
