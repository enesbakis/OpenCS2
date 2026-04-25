# Configuration Reference

All configuration is done through environment variables, typically in a `.env` file in the project root.

## Panel Settings

| Variable | Default | Required | Description |
|---|---|---|---|
| `SECRET_KEY` | `dev-secret-key-change-in-prod` | **Yes** | Flask session signing key. Use a long random string. |
| `DATABASE` | `/app/data/panel.db` | No | Path to the SQLite database file inside the container. |
| `PANEL_ADMIN_USER` | `admin` | No | Username for the initial admin account (created on first start). |
| `PANEL_ADMIN_PASS` | `changeme` | No | Password for the initial admin account. |
| `PANEL_PORT` | `5000` | No | Host port the panel listens on (docker-compose only). |

## RCON Settings

| Variable | Default | Required | Description |
|---|---|---|---|
| `RCON_PASSWORD` | *(empty)* | **Yes** | Must match the CS2 `rcon_password` cvar. |
| `RCON_HOST` | `cs2` | No | Hostname or IP of the CS2 server (Docker service name or external IP). |
| `RCON_PORT` | `27015` | No | RCON TCP port. |

## Server Display Settings

| Variable | Default | Description |
|---|---|---|
| `SERVER_IP` | `127.0.0.1` | Public IP displayed in the panel connect button. |
| `CS2_PORT` | `27015` | Game port (display only). |
| `CS2_MAXPLAYERS` | `0` | Max players (display only; 0 = read from server). |
| `CS2_DATA_PATH` | `/cs2-data` | Path to the CS2 data volume (for map / plugin management). |

## CS2 Server Settings (bundled `cs2` service)

| Variable | Default | Description |
|---|---|---|
| `CS2_SERVERNAME` | `CS2 Server` | Server name shown in browser. |
| `CS2_PASSWORD` | *(empty)* | Server connect password (blank = public). |
| `CS2_STARTMAP` | `de_dust2` | Map loaded on startup. |
| `CS2_GAMETYPE` | `0` | Game type (0 = Casual/Competitive). |
| `CS2_GAMEMODE` | `1` | Game mode. |
| `CS2_MAPGROUP` | `mg_active` | Map group for map rotation. |
| `CS2_LOG` | `on` | Enable server logging. |
| `CS2_LOG_FILE` | `1` | Write logs to file. |
| `CS2_GSLT` | *(empty)* | Steam Game Server Login Token (from [steamcommunity.com/dev/managegameservers](https://steamcommunity.com/dev/managegameservers)). |

## Generating a secure SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
