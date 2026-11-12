# Changelog

All notable changes to OpenCS2 are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security
- CSRF protection on all forms and AJAX requests (Flask-WTF)
- Role-based access control (viewer / operator / admin) with route-level authorization
- Fixed: users could change other users' passwords. Now only admins can change another user's password, and users changing their own password must enter the current one
- Changing a password invalidates all other sessions of that user
- Fixed open redirect in login and language switch (`next` parameter)
- `SECRET_KEY` is now required (the app refuses to start with a missing, short or placeholder key); removed the fixed default admin password
- Fixed directory prefix check bug in plugin config editing
- Tar archives are extracted with `filter='data'` (prevents symlink escape)
- Blocked console command injection via the server name and server password fields
- Upload size limit (`MAX_UPLOAD_MB`)
- Security headers and cookie flags (`SESSION_COOKIE_SECURE`)
- Removed debug endpoints (`/api/debug_rcon`, `/maps/debug`)

### Changed
- Logout is now a `POST` request
- Minimum password length is 8 characters
- RCON console, server restart, player actions, CS2 admin actions, plugin config saves and logins are recorded in the audit log
- New users default to the `viewer` role
- Users must log in again once after upgrading

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
