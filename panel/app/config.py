import os
from datetime import timedelta


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Placeholder secrets that have shipped in this repository's defaults or docs.
# The app refuses to start with any of these (see create_app).
INSECURE_SECRET_KEYS = frozenset({
    "",
    "dev-secret-key-change-in-prod",
    "please-change-this-to-a-random-secret-key",
    "change-this-to-a-long-random-secret-key",
    "change-me",
    "changeme",
})


class Config:
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
    DATABASE: str = os.environ.get("DATABASE", "/app/data/panel.db")
    CS2_DATA_PATH: str = os.environ.get("CS2_DATA_PATH", "/cs2-data")

    RCON_HOST: str = os.environ.get("RCON_HOST", "cs2")
    RCON_PORT: int = int(os.environ.get("RCON_PORT", 27015))
    RCON_PASSWORD: str = os.environ.get("RCON_PASSWORD", "")

    SERVER_IP: str = os.environ.get("SERVER_IP", "127.0.0.1")
    CS2_PORT: int = int(os.environ.get("CS2_PORT", 27015))
    CS2_MAXPLAYERS: int = int(os.environ.get("CS2_MAXPLAYERS", 0))

    # ── Session / cookie hardening ────────────────────────────────────────────
    # Set SESSION_COOKIE_SECURE=true when the panel is served over HTTPS
    # (e.g. behind a reverse proxy). It is off by default because many panels
    # are reached over plain HTTP on a LAN, where secure cookies would break login.
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_DURATION: timedelta = timedelta(days=14)

    # ── CSRF (Flask-WTF) ──────────────────────────────────────────────────────
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT = None  # token valid for the lifetime of the session

    # ── Uploads ───────────────────────────────────────────────────────────────
    # Workshop maps can be large; requests above this size are rejected (413).
    MAX_CONTENT_LENGTH: int = int(os.environ.get("MAX_UPLOAD_MB", 1024)) * 1024 * 1024

    BABEL_DEFAULT_LOCALE: str = "en"
    BABEL_DEFAULT_TIMEZONE: str = "UTC"

    SUPPORTED_LANGUAGES: dict = {
        "en": "English",
        "tr": "Türkçe",
    }

    @property
    def LANGUAGES(self) -> dict:
        return self.SUPPORTED_LANGUAGES
