# Installation Guide

## Prerequisites

- **Docker** ≥ 24.0
- **Docker Compose** v2 (`docker compose` command, not `docker-compose`)
- A Linux host (Ubuntu 22.04 / Debian 12 recommended)
- Open ports: `27015/tcp+udp` (CS2), `5000/tcp` (panel)

## 1. Clone the repository

```bash
git clone https://github.com/enesbakis/OpenCS2.git
cd OpenCS2
```

## 2. Create the environment file

```bash
cp .env.example .env
nano .env   # or use any text editor
```

At minimum, set these three values:

```env
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
RCON_PASSWORD=your_secure_rcon_password
SERVER_IP=YOUR_PUBLIC_IP
```

## 3. Start the services

```bash
docker compose up -d
```

This starts both the CS2 server and the OpenCS2 panel.  
Wait ~60 seconds for CS2 to finish loading, then open:

```
http://YOUR_SERVER_IP:5000
```

Default credentials: **admin / changeme** — change immediately.

## 4. Verify health

```bash
docker compose ps
# Both services should show "healthy" or "running"

curl http://localhost:5000/health
# {"status": "ok"}
```

## Updating

```bash
git pull
docker compose build panel
docker compose up -d panel
```

## Uninstall

```bash
docker compose down -v   # removes containers and named volumes
```

> **Warning**: `-v` deletes the panel database and CS2 data. Backup first.
