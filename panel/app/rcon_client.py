"""
Source RCON client — compatible with CS2 (standard Source RCON protocol).
Each call opens a new TCP connection, authenticates, sends the command,
collects the response using a terminator packet, then closes the socket.
"""

import re
import socket
import struct
import logging

logger = logging.getLogger(__name__)

SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH = 3
SERVERDATA_RESPONSE_VALUE = 0
SERVERDATA_AUTH_RESPONSE = 2


class RCONError(Exception):
    pass


class RCONAuthError(RCONError):
    pass


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _pack(req_id: int, req_type: int, body: str) -> bytes:
    payload = body.encode('utf-8') + b'\x00\x00'
    size = 4 + 4 + len(payload)
    return struct.pack('<iii', size, req_id, req_type) + payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RCONError("Connection closed unexpectedly")
        buf += chunk
    return buf


def _recv_packet(sock: socket.socket):
    raw = _recv_exact(sock, 4)
    size = struct.unpack('<i', raw)[0]
    if not (10 <= size <= 16384):
        raise RCONError(f"Invalid packet size: {size}")
    data = _recv_exact(sock, size)
    req_id = struct.unpack('<i', data[0:4])[0]
    req_type = struct.unpack('<i', data[4:8])[0]
    body = data[8:-2].decode('utf-8', errors='replace')
    return req_id, req_type, body


# ── Public API ─────────────────────────────────────────────────────────────────

def rcon_execute(host: str, port: int, password: str, command: str, timeout: int = 5) -> str:
    """Connect, authenticate, execute *command*, return response string."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, int(port)))

        # ── Authenticate
        sock.sendall(_pack(1, SERVERDATA_AUTH, password))
        req_id, req_type, _ = _recv_packet(sock)
        if req_type == SERVERDATA_RESPONSE_VALUE:          # empty value packet first
            req_id, req_type, _ = _recv_packet(sock)
        if req_id == -1:
            raise RCONAuthError("RCON authentication failed — check your password")

        # ── Execute command + terminator
        sock.sendall(_pack(2, SERVERDATA_EXECCOMMAND, command))
        sock.sendall(_pack(3, SERVERDATA_EXECCOMMAND, ''))

        # Collect response until terminator echoes back
        parts = []
        while True:
            r_id, _, body = _recv_packet(sock)
            if r_id == 3:
                break
            parts.append(body)

        return ''.join(parts).strip()

    except RCONError:
        raise
    except socket.timeout:
        raise RCONError("RCON connection timed out")
    except ConnectionRefusedError:
        raise RCONError("RCON connection refused — server may not be ready")
    except OSError as exc:
        raise RCONError(f"RCON connection error: {exc}")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_cvar(host: str, port: int, password: str, cvar: str) -> str | None:
    """Return the string value of *cvar*, or None on failure."""
    try:
        resp = rcon_execute(host, port, password, cvar)
        # Format 1: "cvar" = "value"  (SourceMod / some CS2 builds)
        m = re.search(r'"' + re.escape(cvar) + r'"\s*=\s*"([^"]*)"', resp)
        if m:
            return m.group(1)
        # Format 2: cvar = "value"  (CS2 default)
        m = re.search(re.escape(cvar) + r'\s*=\s*"([^"]*)"', resp)
        if m:
            return m.group(1)
        # Format 3: cvar = value (unquoted)
        m = re.search(re.escape(cvar) + r'\s*=\s*(\S+)', resp)
        if m:
            val = m.group(1)
            if val != cvar:
                return val
    except RCONError:
        pass
    return None


# ── Status parser ──────────────────────────────────────────────────────────────

def parse_status(output: str) -> dict:
    """
    Parse the output of the CS2 ``status`` command.

    Actual CS2 format (2024+):
        hostname : <name>
        players  : 1 humans, 1 bots (0 max) (not hibernating) (unreserved)
        ---------players--------
          id     time ping loss      state   rate adr name
           2    01:47    9    0     active 786432 78.190.129.63:8333 'Ergenekondom'
        #end

    Map is extracted from spawngroup line:
        loaded spawngroup(  1)  : SV:  [1: de_dust2 | main lump | mapload]
    """
    info = {
        'hostname': 'Unknown',
        'map': 'Unknown',
        'player_count': 0,
        'max_players': 0,
        'bot_count': 0,
        'players': [],
        'ip': '',
        'version': '',
    }

    in_player_section = False

    for line in output.splitlines():
        s = line.strip()

        # hostname : CS2 Server
        if re.match(r'hostname\s*:', s):
            info['hostname'] = s.split(':', 1)[1].strip()

        # players  : 1 humans, 1 bots (0 max) ...
        elif re.match(r'players\s*:', s):
            m = re.search(r'(\d+)\s+human', s)
            if m:
                info['player_count'] = int(m.group(1))
            m = re.search(r'(\d+)\s+bot', s)
            if m:
                info['bot_count'] = int(m.group(1))
            # max players genellikle 0 gösterir, mapcycle'dan alınır

        # udp/ip   : 0.0.0.0:27015 (public 93.88.201.20:27015)
        elif re.match(r'udp/ip\s*:', s) or re.match(r'tcp/ip\s*:', s):
            part = s.split(':', 1)[1].strip()
            info['ip'] = part.split()[0]

        # version  : 1.41.5.4/14154 ...
        elif re.match(r'version\s*:', s):
            info['version'] = s.split(':', 1)[1].strip()

        # loaded spawngroup(  1)  : SV:  [1: de_dust2 | main lump | mapload]
        # İlk spawngroup = ana harita
        elif info['map'] == 'Unknown' and 'spawngroup' in s:
            m = re.search(r'\[\d+:\s*([^|]+?)\s*\|', s)
            if m:
                candidate = m.group(1).strip()
                # "maps/" prefix'ini temizle
                candidate = re.sub(r'^maps/', '', candidate)
                info['map'] = candidate

        # Player section header
        elif '---players---' in s or s == '---------players--------':
            in_player_section = True
            continue

        # Any other section header resets player section
        elif s.startswith('---') and in_player_section and 'players' not in s:
            in_player_section = False

        # #end
        elif s == '#end':
            in_player_section = False

        # Header row: skip
        elif in_player_section and re.match(r'id\s+time', s):
            continue

        # Player row inside player section
        # Format:    id  time/BOT/[NoChan]  ping  loss  state  rate  [adr]  'name'
        elif in_player_section and s:
            # Real player: has ip:port address and numeric id
            # e.g.: "   2    01:47    9    0     active 786432 78.190.129.63:8333 'Ergenekondom'"
            m = re.match(
                r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s+\d+\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)\s+'(.*)'\s*$",
                line,
            )
            if m:
                userid, time_val, ping, loss, state, adr, name = (
                    m.group(1), m.group(2), m.group(3),
                    m.group(4), m.group(5), m.group(6), m.group(7),
                )
                if name:  # boş isimli (spectator slot vs.) atla
                    info['players'].append({
                        'userid': userid,
                        'name': name,
                        'steamid': adr,  # CS2 RCON status steamid vermez, ip:port kullan
                        'connected': time_val,
                        'ping': ping,
                        'loss': loss,
                        'state': state,
                    })

    return info
