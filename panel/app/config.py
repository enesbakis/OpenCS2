import os


class Config:
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
    DATABASE: str = os.environ.get("DATABASE", "/app/data/panel.db")
    CS2_DATA_PATH: str = os.environ.get("CS2_DATA_PATH", "/cs2-data")

    RCON_HOST: str = os.environ.get("RCON_HOST", "cs2")
    RCON_PORT: int = int(os.environ.get("RCON_PORT", 27015))
    RCON_PASSWORD: str = os.environ.get("RCON_PASSWORD", "")

    SERVER_IP: str = os.environ.get("SERVER_IP", "127.0.0.1")
    CS2_PORT: int = int(os.environ.get("CS2_PORT", 27015))
    CS2_MAXPLAYERS: int = int(os.environ.get("CS2_MAXPLAYERS", 0))

    BABEL_DEFAULT_LOCALE: str = "en"
    BABEL_DEFAULT_TIMEZONE: str = "UTC"

    SUPPORTED_LANGUAGES: dict = {
        "en": "English",
        "tr": "Türkçe",
    }

    @property
    def LANGUAGES(self) -> dict:
        return self.SUPPORTED_LANGUAGES
