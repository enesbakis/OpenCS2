# Changelog

All notable changes to OpenCS2 are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

---

## [1.0.0] - 2026-04-25

### Added
- Web panel for CS2 dedicated server management
- Dashboard with live RCON server status and player list
- Map management (change map, manage map groups)
- CounterStrikeSharp plugin manager (install / remove)
- CS2 admin and group manager
- Metamod:Source and CounterStrikeSharp toggle
- Multi-user management with role-based access
- Full audit log of all panel actions
- Internationalization: English and Turkish UI (Flask-Babel)
- Docker Compose deployment (CS2 + panel)
- SQLite database (no external DB required)
- CI workflow (flake8 lint + import test)
- Docker image published to GHCR (`ghcr.io/enesbakis/opencs2`)

[Unreleased]: https://github.com/enesbakis/OpenCS2/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/enesbakis/OpenCS2/releases/tag/v1.0.0
