#!/usr/bin/env python3
"""
Homelab Deploy Tool
Interactive CLI for configuring and deploying homelab services via Docker Compose.
"""

import os
import re
import secrets
import shutil
import subprocess
import sys

# ── Venv bootstrap ────────────────────────────────────────────────────────────
# Creates .venv on first run, installs deps, re-execs itself inside it.

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
VENV_DIR    = os.path.join(SCRIPT_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python") if os.name != "nt" \
              else os.path.join(VENV_DIR, "Scripts", "python.exe")

def in_venv():
    return sys.prefix != sys.base_prefix

if not in_venv():
    if not os.path.exists(VENV_PYTHON):
        print("Setting up environment (first run only)...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    subprocess.check_call([VENV_PYTHON, "-m", "pip", "install", "questionary", "-q"])
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import questionary
from questionary import Style, Choice, Separator

# ── Catppuccin Mocha ──────────────────────────────────────────────────────────

MOCHA = Style([
    ("qmark",       "fg:#cba6f7 bold"),
    ("question",    "fg:#cdd6f4 bold"),
    ("answer",      "fg:#a6e3a1 bold"),
    ("pointer",     "fg:#cba6f7 bold"),
    ("highlighted", "fg:#cba6f7 bold"),
    ("selected",    "fg:#a6e3a1"),
    ("separator",   "fg:#45475a"),
    ("instruction", "fg:#7f849c"),
    ("text",        "fg:#cdd6f4"),
    ("disabled",    "fg:#585b70 italic"),
])

RESET   = "\033[0m"
MAUVE   = "\033[38;2;203;166;247m"
TEXT    = "\033[38;2;205;214;244m"
SUBTEXT = "\033[38;2;127;132;156m"
GREEN   = "\033[38;2;166;227;161m"
YELLOW  = "\033[38;2;249;226;175m"
RED     = "\033[38;2;243;139;168m"
BLUE    = "\033[38;2;137;180;250m"
SURFACE = "\033[38;2;69;71;90m"

# ── Timezone list ─────────────────────────────────────────────────────────────

TIMEZONES = {
    "Americas": [
        "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
        "America/Phoenix", "America/Anchorage", "America/Honolulu", "America/Toronto",
        "America/Vancouver", "America/Edmonton", "America/Winnipeg", "America/Halifax",
        "America/St_Johns", "America/Mexico_City", "America/Sao_Paulo", "America/Buenos_Aires",
        "America/Bogota", "America/Lima", "America/Santiago", "America/Caracas",
    ],
    "Europe": [
        "Europe/London", "Europe/Dublin", "Europe/Lisbon", "Europe/Paris", "Europe/Berlin",
        "Europe/Madrid", "Europe/Rome", "Europe/Amsterdam", "Europe/Brussels", "Europe/Zurich",
        "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Helsinki",
        "Europe/Warsaw", "Europe/Prague", "Europe/Vienna", "Europe/Budapest",
        "Europe/Bucharest", "Europe/Athens", "Europe/Istanbul", "Europe/Moscow",
    ],
    "Asia / Pacific": [
        "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok",
        "Asia/Singapore", "Asia/Kuala_Lumpur", "Asia/Hong_Kong", "Asia/Shanghai",
        "Asia/Tokyo", "Asia/Seoul", "Asia/Taipei",
        "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane",
        "Australia/Adelaide", "Australia/Perth", "Pacific/Auckland", "Pacific/Fiji",
    ],
    "Africa / Other": [
        "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
        "UTC",
    ],
}

# Flat lookup for timezone detection
TIMEZONES_FLAT = [tz for tzs in TIMEZONES.values() for tz in tzs]

# ── NAS device presets ────────────────────────────────────────────────────────

NAS_DEVICES = {
    "synology": {
        "name":    "Synology DSM",
        "hint":    "Shared folders live under /volume1/ (or /volume2/, etc.)",
        "example": "/volume1/homelab",
    },
    "qnap": {
        "name":    "QNAP QTS / QuTS Hero",
        "hint":    "Shared folders live under /share/",
        "example": "/share/homelab",
    },
    "truenas": {
        "name":    "TrueNAS / FreeNAS",
        "hint":    "Datasets are under /mnt/<pool>/",
        "example": "/mnt/tank/homelab",
    },
    "unifi": {
        "name":     "Unifi Dream Machine (NFS)",
        "hint":     "Shares live on the UDM; reference the NFS export path directly",
        "example":  "/var/nfs/shared/homelab",
        "template": "/var/nfs/shared/[ShareName]/[PathToFolder]",
    },
    "nfs": {
        "name":     "Generic NFS mount",
        "hint":     "Use the local mount point on this machine (e.g. /mnt/nas)",
        "example":  "/mnt/nas/homelab",
        "template": "/mnt/[mountpoint]/[PathToFolder]",
    },
    "smb": {
        "name":     "SMB / Windows share",
        "hint":     "Use the local path this machine maps the share to",
        "example":  "/mnt/nas/homelab",
        "template": "/mnt/[sharename]/[PathToFolder]",
    },
    "local": {
        "name":    "Local directory (no NAS)",
        "hint":    "Data stays on this machine; subfolders created under ./data/ automatically",
        "example": "./data",
    },
}

SUBFOLDER_KEYS = {
    "NAS_MEDIA_PATH":     "media",
    "NAS_MUSIC_PATH":     "music",
    "NAS_BOOKS_PATH":     "books",
    "NAS_PHOTOS_PATH":    "photos",
    "NAS_DOCUMENTS_PATH": "documents",
}

# ── Generic env sections (handled by the standard loop) ───────────────────────

ENV_SECTIONS = [
    {
        "name": "AdGuard Home",
        "desc": "DNS & ad blocking credentials",
        "vars": [
            {"key": "ADGUARD_USERNAME", "desc": "Admin username", "default": "admin"},
            {"key": "ADGUARD_PASSWORD", "desc": "Admin password", "default": "changeme", "password": True},
        ],
    },
    {
        "name": "Passwords",
        "desc": "Database passwords for all services",
        "bulk_password": True,
        "vars": [
            {"key": "MEALIE_DB_PASSWORD",      "desc": "Mealie database password",    "default": "changeme", "password": True},
            {"key": "MEALIE_SECRET_KEY",        "desc": "Mealie secret key",           "default": "changeme", "password": True},
            {"key": "PAPERLESS_DB_PASSWORD",    "desc": "Paperless database password", "default": "changeme", "password": True},
            {"key": "PAPERLESS_SECRET_KEY",     "desc": "Paperless secret key",        "default": "changeme", "password": True},
            {"key": "PAPERLESS_ADMIN_USER",     "desc": "Paperless admin username",    "default": "admin"},
            {"key": "PAPERLESS_ADMIN_PASSWORD", "desc": "Paperless admin password",    "default": "changeme", "password": True},
            {"key": "IMMICH_DB_PASSWORD",       "desc": "Immich database password",    "default": "changeme", "password": True},
            {"key": "IMMICH_DB_USERNAME",       "desc": "Immich database username",    "default": "immich"},
            {"key": "IMMICH_DB_NAME",           "desc": "Immich database name",        "default": "immich"},
            {"key": "N8N_ENCRYPTION_KEY",       "desc": "n8n encryption key",          "default": "changeme", "password": True},
            {"key": "KOEL_DB_PASSWORD",         "desc": "Koel database password",      "default": "changeme", "password": True},
            {"key": "METABASE_DB_PASSWORD",     "desc": "Metabase database password",  "default": "changeme", "password": True},
            {"key": "PASTEFY_DB_PASSWORD",      "desc": "Pastefy database password",   "default": "changeme", "password": True},
            {"key": "NOCODB_DB_PASSWORD",       "desc": "NocoDB database password",    "default": "changeme", "password": True},
        ],
    },
    {
        "name": "Setup Homepage API Keys",
        "desc": "Optional — fill in after services are running to enable dashboard widgets",
        "optional": True,
        "vars": [
            {"key": "HOMEPAGE_VAR_JELLYFIN",        "desc": "Jellyfin API key",  "default": ""},
            {"key": "HOMEPAGE_VAR_JELLYSEER",       "desc": "Jellyseer API key", "default": ""},
            {"key": "HOMEPAGE_VAR_ADGUARD_USERNAME","desc": "AdGuard username",  "default": "admin"},
            {"key": "HOMEPAGE_VAR_ADGUARD_PASSWORD","desc": "AdGuard password",  "default": "changeme"},
            {"key": "HOMEPAGE_VAR_PORTAINER_KEY",   "desc": "Portainer API key", "default": ""},
        ],
    },
]

# ── Service definitions ───────────────────────────────────────────────────────

CORE = [
    {"id": "nginx-proxy-manager", "name": "Nginx Proxy Manager", "desc": "Reverse proxy & SSL termination", "port": 81},
    {"id": "adguard",             "name": "AdGuard Home",         "desc": "DNS & ad blocking",              "port": 3000},
]

CATEGORIES = [
    {
        "id": "media", "name": "Media", "desc": "Streaming and music",
        "services": [
            {"id": "jellyfin",  "name": "Jellyfin",  "desc": "Media server",    "port": 8096},
            {"id": "jellyseer", "name": "Jellyseer", "desc": "Media requests",  "port": 5055, "requires": ["jellyfin"]},
            {"id": "koel",      "name": "Koel",       "desc": "Music streaming", "port": 4533},
        ],
    },
    {
        "id": "photos", "name": "Photos", "desc": "Photo backup and management",
        "services": [
            {"id": "immich", "name": "Immich", "desc": "Photo management & ML search", "port": 2283},
        ],
    },
    {
        "id": "productivity", "name": "Productivity", "desc": "Recipes, documents, and automation",
        "services": [
            {"id": "mealie",        "name": "Mealie",        "desc": "Recipe manager",       "port": 9000},
            {"id": "paperless-ngx", "name": "Paperless-NGX", "desc": "Document management",  "port": 8001},
            {"id": "n8n",           "name": "n8n",           "desc": "Workflow automation",   "port": 5678},
        ],
    },
    {
        "id": "dashboard", "name": "Dashboards", "desc": "Service overview and content feeds",
        "services": [
            {"id": "homepage", "name": "Homepage", "desc": "Service dashboard",       "port": 3001},
            {"id": "glance",   "name": "Glance",   "desc": "News & content dashboard","port": 8181},
        ],
    },
    {
        "id": "books", "name": "Books", "desc": "Reading and book management",
        "services": [
            {"id": "kavita",      "name": "Kavita",      "desc": "Book reader",            "port": 5001},
            {"id": "calibre-web", "name": "Calibre Web", "desc": "Book library",           "port": 8083},
        ],
    },
    {
        "id": "dev", "name": "Dev Tools", "desc": "Databases, analytics, and utilities",
        "services": [
            {"id": "nocodb",    "name": "NocoDB",    "desc": "No-code database UI",   "port": 8082},
            {"id": "metabase",  "name": "Metabase",  "desc": "Analytics & BI",        "port": 3002},
            {"id": "pastefy",   "name": "Pastefy",   "desc": "Paste service",          "port": 4567},
            {"id": "bytestash", "name": "Bytestash", "desc": "Code snippet manager",   "port": 5003},
        ],
    },
]

# ── .env helpers ──────────────────────────────────────────────────────────────

ENV_FILE    = os.path.join(SCRIPT_DIR, ".env")
ENV_EXAMPLE = os.path.join(SCRIPT_DIR, ".env.example")

def load_env():
    values = {}
    if not os.path.exists(ENV_FILE):
        return values
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip()
    return values

def save_env(values):
    if not os.path.exists(ENV_EXAMPLE):
        with open(ENV_FILE, "w") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")
        return
    with open(ENV_EXAMPLE) as f:
        template = f.read()
    def replacer(match):
        key = match.group(1)
        return f"{key}={values.get(key, match.group(2))}"
    result = re.sub(r"^([A-Z0-9_]+)=(.*)$", replacer, template, flags=re.MULTILINE)
    with open(ENV_FILE, "w") as f:
        f.write(result)

def gen_password(length=32):
    return secrets.token_urlsafe(length)

# ── Wizard helpers ────────────────────────────────────────────────────────────

# ── Pure-Python NFSv3 path checker ───────────────────────────────────────────
# Uses raw sockets + XDR/SunRPC — no OS tools, no extra packages required.

import random
import struct
import socket as _socket
import time as _time

def _xdr_uint(v):
    return struct.pack(">I", v)

def _xdr_str(s):
    if isinstance(s, str):
        s = s.encode()
    n = len(s)
    return struct.pack(">I", n) + s + b"\x00" * ((-n) % 4)

_xdr_opaque = _xdr_str  # same wire format

def _rd_uint(buf, o):
    v, = struct.unpack_from(">I", buf, o)
    return v, o + 4

def _rd_opaque(buf, o):
    n, o = _rd_uint(buf, o)
    return buf[o : o + n], o + n + ((-n) % 4)

_AUTH_NONE = _xdr_uint(0) + _xdr_uint(0)  # flavor=AUTH_NONE, body=empty

def _auth_sys(uid=0, gid=0):
    """Build AUTH_SYS (flavor=1) credentials — required by most NFS servers."""
    body = (
        _xdr_uint(int(_time.time()) & 0xFFFFFFFF) +  # stamp
        _xdr_str(b"homelab") +                        # machine name
        _xdr_uint(uid) +                              # uid
        _xdr_uint(gid) +                              # gid
        _xdr_uint(0)                                  # no auxiliary gids
    )
    return _xdr_uint(1) + _xdr_opaque(body)           # flavor=1 + body

def _try_resvport(sock, proto):
    """
    Bind sock to a random privileged port (600-1023) — equivalent to -o resvport.
    Many NFS servers require the client to use a source port < 1024 ("secure" exports).
    Silently skips if we lack permission (non-root); portmapper/EXPORTLIST still work,
    but MOUNT will be rejected with stat=13 until run as root/sudo.
    """
    candidates = list(range(600, 1024))
    random.shuffle(candidates)
    for p in candidates:
        try:
            sock.bind(('', p))
            return
        except OSError:
            pass

def _rpc_call(host, port, prog, ver, proc, body, auth=None, timeout=5):
    creds = auth if auth is not None else _AUTH_NONE
    xid   = random.randint(1, 0xFFFFFFFF)
    msg   = (
        _xdr_uint(xid)  + _xdr_uint(0) + _xdr_uint(2) +
        _xdr_uint(prog) + _xdr_uint(ver) + _xdr_uint(proc) +
        creds + _AUTH_NONE +                           # creds + verifier (always NONE)
        body
    )
    frame = struct.pack(">I", 0x80000000 | len(msg)) + msg

    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    s.settimeout(timeout)
    _try_resvport(s, 'tcp')
    try:
        s.connect((host, port))
        s.sendall(frame)
        # RFC 5531 §11: TCP uses record-mark framing; high bit = last-fragment.
        # A reply may span multiple fragments — accumulate until last-fragment seen.
        reply = b""
        while True:
            rm = b""
            while len(rm) < 4:
                rm += s.recv(4 - len(rm))
            hdr       = struct.unpack(">I", rm)[0]
            last_frag = bool(hdr & 0x80000000)
            frag_len  = hdr & 0x7FFFFFFF
            frag = b""
            while len(frag) < frag_len:
                frag += s.recv(frag_len - len(frag))
            reply += frag
            if last_frag:
                break
    finally:
        s.close()

    o = 12
    _, o = _rd_uint(reply, o)
    _, o = _rd_opaque(reply, o)
    stat, o = _rd_uint(reply, o)
    if stat != 0:
        raise OSError(f"RPC accept_stat={stat}")
    return reply, o

def _rpc_call_udp(host, port, prog, ver, proc, body, auth=None, timeout=5):
    """Sun RPC over UDP — no record mark framing."""
    creds = auth if auth is not None else _AUTH_NONE
    xid   = random.randint(1, 0xFFFFFFFF)
    msg   = (
        _xdr_uint(xid) + _xdr_uint(0) + _xdr_uint(2) +
        _xdr_uint(prog) + _xdr_uint(ver) + _xdr_uint(proc) +
        creds + _AUTH_NONE +
        body
    )
    with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        _try_resvport(s, 'udp')
        s.sendto(msg, (host, port))
        reply, _ = s.recvfrom(65536)
    o = 12
    _, o = _rd_uint(reply, o)
    _, o = _rd_opaque(reply, o)
    stat, o = _rd_uint(reply, o)
    if stat != 0:
        raise OSError(f"RPC accept_stat={stat}")
    return reply, o

def _portmap_getport(host, prog, ver, proto=6):
    """
    Ask the portmapper (port 111) for the port of a given program.
    Uses PMAPPROC_GETPORT = procedure 3 (RFC 1833 portmapper v2).
    Tries TCP first, then UDP — some embedded devices only answer UDP.
    """
    body = _xdr_uint(prog) + _xdr_uint(ver) + _xdr_uint(proto) + _xdr_uint(0)
    try:
        reply, o = _rpc_call(host, 111, 100000, 2, 3, body)
    except Exception:
        reply, o = _rpc_call_udp(host, 111, 100000, 2, 3, body)
    port, _ = _rd_uint(reply, o)
    return port

def diagnose_nfs(nas_ip):
    """Print step-by-step NFS connectivity diagnostics."""
    print(f"\n  {BLUE}NFS diagnostics — {nas_ip}{RESET}\n")

    def check(label, fn):
        print(f"  {SUBTEXT}{label}...{RESET}", end="", flush=True)
        try:
            result = fn()
            print(f"\r  {GREEN}✓{RESET}  {label:<44} {TEXT}{result or ''}{RESET}")
            return result
        except Exception as e:
            print(f"\r  {RED}✗{RESET}  {label:<44} {SUBTEXT}{e}{RESET}")
            return None

    # Port reachability
    def tcp111():
        _socket.create_connection((nas_ip, 111), timeout=3).close()
        return "open"
    def tcp2049():
        _socket.create_connection((nas_ip, 2049), timeout=3).close()
        return "open"

    port111  = check("Port 111 TCP (portmapper)", tcp111)
    port2049 = check("Port 2049 TCP (NFS)",       tcp2049)

    # Portmapper RPC
    mountd_port = check(
        "Portmapper: find mountd",
        lambda: _portmap_getport(nas_ip, 100005, 3) or "—",
    )

    if mountd_port and mountd_port != "—":
        exports = check(
            f"MOUNT EXPORTLIST on port {mountd_port}",
            lambda: ", ".join(_mount_exports(nas_ip, int(mountd_port))) or "(none)",
        )
        nfs_port = check(
            "Portmapper: find NFS (TCP)",
            lambda: _portmap_getport(nas_ip, 100003, 3, proto=6),
        )
        if nfs_port and exports:
            first_export = _mount_exports(nas_ip, int(mountd_port))[0]
            fh = check(
                f"MOUNT MNT {first_export}",
                lambda: f"{len(_mount_mnt(nas_ip, int(mountd_port), first_export))} byte handle",
            )
    print()

def _export_label(path):
    """
    Return a human-readable label for an NFS export path.
    Unifi exports look like /volume/<UUID>/.srv/.unifi-drive/<Name>/.data
    — we extract just <Name>.
    """
    import re as _re
    m = _re.search(r"\.unifi-drive/([^/]+)", path)
    if m:
        return m.group(1)
    # Generic fallback: last non-hidden, short component
    parts = [p for p in path.split("/") if p and not p.startswith(".") and len(p) < 40]
    return parts[-1] if parts else path

def _normalize_export(path):
    """
    Unifi registers internal UUID paths with portmapper, but NFS ACLs are
    applied to the user-visible /var/nfs/shared/<Name> path. Convert so
    we mount the path the user actually configured access for.
    Input:  /volume/<UUID>/.srv/.unifi-drive/<Name>/.data
    Output: /var/nfs/shared/<Name>
    """
    import re as _re
    m = _re.search(r"\.unifi-drive/([^/]+)", path)
    if m:
        return f"/var/nfs/shared/{m.group(1)}"
    return path  # unchanged for non-Unifi

def _mount_exports(host, port):
    """List NFS exports via MOUNT EXPORTLIST (proc 5)."""
    reply, o = _rpc_call(host, port, 100005, 3, 5, b"", auth=_auth_sys())
    exports = []
    while o < len(reply):
        vf, o = _rd_uint(reply, o)
        if not vf:
            break
        ex, o = _rd_opaque(reply, o)
        exports.append(ex.decode())
        # skip group list
        while o < len(reply):
            gf, o = _rd_uint(reply, o)
            if not gf:
                break
            _, o = _rd_opaque(reply, o)
    return exports

_MOUNT_ERRORS = {
    1:     "permission denied",
    2:     "no such file or directory",
    5:     "I/O error",
    13:    "access denied — this host is not in the NFS export's allowed client list",
    20:    "not a directory",
    22:    "invalid argument",
    63:    "name too long",
    10004: "operation not supported",
    10006: "server fault",
}

def _mount_mnt(host, port, path, udp=False):
    """
    Mount a path and return its NFSv3 file handle.
    Tries TCP first; pass udp=True to use UDP transport.
    """
    call = _rpc_call_udp if udp else _rpc_call
    reply, o = call(host, port, 100005, 3, 1, _xdr_str(path), auth=_auth_sys())
    stat, o  = _rd_uint(reply, o)
    if stat != 0:
        raise OSError(_MOUNT_ERRORS.get(stat, f"error code {stat}"))
    fh, _ = _rd_opaque(reply, o)
    return fh

def _mount_umnt(host, port, path, udp=False):
    """Send MOUNT UMNT (proc 3) to remove this host from the server's mount list."""
    try:
        call = _rpc_call_udp if udp else _rpc_call
        call(host, port, 100005, 3, 3, _xdr_str(path), auth=_auth_sys())
    except Exception:
        pass  # best-effort; server state is advisory only

def _nfs_mkdir(host, port, parent_fh, name, mode=0o755):
    """NFSv3 MKDIR (proc 9): create a directory under parent_fh."""
    sattr = (
        _xdr_uint(1) + _xdr_uint(mode) +   # set_mode = 0755
        _xdr_uint(0) +                       # set_uid:   DONT_CHANGE
        _xdr_uint(0) +                       # set_gid:   DONT_CHANGE
        _xdr_uint(0) +                       # set_size:  DONT_CHANGE
        _xdr_uint(0) +                       # set_atime: DONT_CHANGE
        _xdr_uint(0)                         # set_mtime: DONT_CHANGE
    )
    body = _xdr_opaque(parent_fh) + _xdr_str(name) + sattr
    reply, o = _rpc_call(host, port, 100003, 3, 9, body, auth=_auth_sys())
    stat, _ = _rd_uint(reply, o)
    if stat != 0:
        raise OSError(f"MKDIR stat={stat}")

def _nfs_lookup(host, port, fh, name):
    """NFSv3 LOOKUP: look up one component; return child filehandle or None."""
    body = _xdr_opaque(fh) + _xdr_str(name)
    try:
        reply, o = _rpc_call(host, port, 100003, 3, 3, body, auth=_auth_sys())
        stat, o  = _rd_uint(reply, o)
        if stat != 0:
            return None
        child, _ = _rd_opaque(reply, o)
        return child
    except Exception:
        return None

def _xdr_uint64(v):
    return struct.pack(">Q", v)

def _rd_uint64(buf, o):
    v, = struct.unpack_from(">Q", buf, o)
    return v, o + 8

def _rd_fattr3(buf, o):
    """Parse fattr3: return (ftype, offset_after). ftype 2 = directory."""
    ftype, o = _rd_uint(buf, o)
    o += 80   # skip mode(4)+nlink(4)+uid(4)+gid(4)+size(8)+used(8)+rdev(8)+fsid(8)+fileid(8)+atime(8)+mtime(8)+ctime(8)
    return ftype, o

def _rd_post_op_attr(buf, o):
    """Parse post_op_attr; return (ftype_or_None, offset_after)."""
    follows, o = _rd_uint(buf, o)
    if follows:
        ftype, o = _rd_fattr3(buf, o)
        return ftype, o
    return None, o

def _rd_post_op_fh3(buf, o):
    """Parse post_op_fh3; return (fh_or_None, offset_after)."""
    follows, o = _rd_uint(buf, o)
    if follows:
        fh, o = _rd_opaque(buf, o)
        return fh, o
    return None, o

def _nfs_readdirplus(host, port, fh):
    """
    NFSv3 READDIRPLUS (proc 17): list a directory.
    Returns [(name, ftype, child_fh)] — ftype 2 = directory.
    """
    # dircount=4096, maxcount=32768
    body = _xdr_opaque(fh) + struct.pack(">QQ", 0, 0) + _xdr_uint(4096) + _xdr_uint(32768)
    try:
        reply, o = _rpc_call(host, port, 100003, 3, 17, body, auth=_auth_sys())
        stat, o  = _rd_uint(reply, o)
        if stat != 0:
            return []
        _, o = _rd_post_op_attr(reply, o)   # skip dir attributes
        o   += 8                             # skip cookieverf (uint64)
        entries = []
        while o < len(reply):
            vf, o = _rd_uint(reply, o)
            if not vf:
                break
            _,     o = _rd_uint64(reply, o)     # fileid
            name,  o = _rd_opaque(reply, o)
            _,     o = _rd_uint64(reply, o)     # cookie
            ftype, o = _rd_post_op_attr(reply, o)
            cfh,   o = _rd_post_op_fh3(reply, o)
            n = name.decode("utf-8", errors="replace")
            if n not in (".", ".."):
                entries.append((n, ftype, cfh))
        return entries
    except Exception:
        return []

def _nfs_connect(nas_ip):
    """
    Connect to NFS server; return (mountd_tcp, mountd_udp, nfs_port, exports).
    A port value of 0 means not available on that transport.
    Raises on failure.
    """
    mountd_tcp  = _portmap_getport(nas_ip, 100005, 3, proto=6)
    mountd_udp  = _portmap_getport(nas_ip, 100005, 3, proto=17)
    nfs_port    = _portmap_getport(nas_ip, 100003, 3, proto=6)
    # Use whichever mountd port is non-zero for export listing
    mountd_port = mountd_tcp or mountd_udp
    if not mountd_port:
        raise OSError("mountd port not found in portmapper")
    exports = _mount_exports(nas_ip, mountd_port)
    return mountd_tcp, mountd_udp, nfs_port, exports

def browse_nfs(nas_ip):
    """
    Interactive NFSv3 directory browser.
    Returns the chosen absolute path string, or None if cancelled.
    """
    try:
        mountd_tcp, mountd_udp, nfs_port, exports = _nfs_connect(nas_ip)
    except Exception:
        return None

    if not exports:
        return None

    # Normalize export paths (Unifi UUID → /var/nfs/shared/<Name>)
    # and build label map for display
    norm_exports = {_normalize_export(e): _export_label(e) for e in exports}

    # Pick export — show human-readable labels, store normalized mount path as value
    if len(norm_exports) == 1:
        export = next(iter(norm_exports))
        print(f"  {SUBTEXT}Export: {norm_exports[export]}{RESET}")
    else:
        export = questionary.select(
            "  NFS share:",
            choices=[
                Choice(label, value=path)
                for path, label in sorted(norm_exports.items(), key=lambda x: x[1])
            ],
            style=MOCHA,
        ).ask()
        if export is None:
            return None

    # Try all combinations: (path, port, udp_transport)
    # Include both the normalized path (/var/nfs/shared/<Name>) and the
    # original UUID path — mountd only registered the UUID path with portmapper,
    # so the normalized alias might be rejected.
    raw_exports  = exports                          # UUID paths from portmapper
    norm_export  = export                           # /var/nfs/shared/<Name>
    uuid_export  = next((e for e in raw_exports
                         if _export_label(e) == _export_label(norm_export)), None)

    paths_to_try = list(dict.fromkeys(filter(None, [norm_export, uuid_export])))
    ports_to_try = []
    if mountd_tcp: ports_to_try += [(mountd_tcp, False), (mountd_tcp, True)]
    if mountd_udp: ports_to_try += [(mountd_udp, True),  (mountd_udp, False)]

    root_fh    = None
    last_error = None
    for mount_path in paths_to_try:
        for port, udp in ports_to_try:
            try:
                root_fh = _mount_mnt(nas_ip, port, mount_path, udp=udp)
                export  = mount_path
                break
            except Exception as e:
                last_error = str(e)
        if root_fh is not None:
            break

    if root_fh is None:
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.connect((nas_ip, 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "unknown"

        print(f"\n  {YELLOW}⚠  NFS mount failed from this machine ({local_ip}).{RESET}")
        if last_error:
            print(f"  {SUBTEXT}Error: {last_error}{RESET}")
        print(f"  {SUBTEXT}NFS servers require a privileged source port — try: sudo python3 deploy.py{RESET}")
        return None

    # Navigation stack: list of (display_path, nfs_export_path, fh)
    # display_path uses the clean label for the export root, then appends real subdir names
    export_label  = _export_label(export)
    export_root   = export.rstrip("/")
    stack = [(export_label, export_root, root_fh)]

    while True:
        display_path, nfs_path, current_fh = stack[-1]
        print(f"\n  {SUBTEXT}Location: {RESET}{TEXT}{display_path}{RESET}")

        raw = _nfs_readdirplus(nas_ip, nfs_port, current_fh)
        dirs = sorted(
            [(n, cfh) for n, ftype, cfh in raw if ftype == 2 and cfh is not None],
            key=lambda x: x[0].lower(),
        )

        choices = []
        if len(stack) > 1:
            choices.append(Choice("  ..  (go up)", value="__back__"))
        choices.append(Choice("  [select this folder]", value="__select__"))
        if dirs:
            choices.append(Separator())
            for name, cfh in dirs:
                choices.append(Choice(f"  {name}/", value=("__enter__", name, cfh)))
        elif len(raw) == 0:
            print(f"  {YELLOW}⚠  Could not read directory contents (empty or permission denied){RESET}")

        action = questionary.select(
            "  Navigate:",
            choices=choices,
            style=MOCHA,
        ).ask()

        if action is None:
            _mount_umnt(nas_ip, mountd_tcp or mountd_udp, export)
            return None
        elif action == "__back__":
            stack.pop()
        elif action == "__select__":
            _mount_umnt(nas_ip, mountd_tcp or mountd_udp, export)
            return nfs_path          # return the real NFS export path
        elif isinstance(action, tuple):
            _, name, cfh = action
            stack.append((
                f"{display_path}/{name}",   # friendly display path
                f"{nfs_path}/{name}",       # real NFS path
                cfh,
            ))

def check_nfs_paths(nas_ip, paths):
    """
    Check remote NFS paths using pure-Python RPC/NFSv3.
    No OS tools or extra packages required.
    Returns {key: bool} on success, or None on any error.
    """
    try:
        mountd_tcp = _portmap_getport(nas_ip, 100005, 3, proto=6)
        mountd_udp = _portmap_getport(nas_ip, 100005, 3, proto=17)
        mountd_port = mountd_tcp or mountd_udp
        if not mountd_port:
            return None

        exports = _mount_exports(nas_ip, mountd_port)
        if not exports:
            return None

        # Normalize Unifi UUID paths → /var/nfs/shared/<Name>
        exports = [_normalize_export(e) for e in exports]

        # Find longest export that is a prefix of our base path
        first = next(iter(paths.values()))
        candidates = sorted(
            [e for e in exports if first.startswith(e)],
            key=len, reverse=True,
        )
        if not candidates:
            return None
        export = candidates[0]

        nfs_port = _portmap_getport(nas_ip, 100003, 3)
        if not nfs_port:
            return None

        root_fh = _mount_mnt(nas_ip, mountd_tcp or mountd_udp, export,
                             udp=(not mountd_tcp and bool(mountd_udp)))

        results = {}
        for key, path in paths.items():
            rel   = path[len(export):].lstrip("/")
            parts = [p for p in rel.split("/") if p]
            fh    = root_fh
            for part in parts:
                fh = _nfs_lookup(nas_ip, nfs_port, fh, part)
                if fh is None:
                    break
            results[key] = fh is not None
        return results

    except Exception:
        return None

def create_nfs_paths(nas_ip, paths):
    """
    Create missing NFS directories via NFSv3 MKDIR.
    Returns {key: True/False} — True = created (or already existed), False = failed.
    """
    try:
        mountd_tcp  = _portmap_getport(nas_ip, 100005, 3, proto=6)
        mountd_udp  = _portmap_getport(nas_ip, 100005, 3, proto=17)
        mountd_port = mountd_tcp or mountd_udp
        nfs_port    = _portmap_getport(nas_ip, 100003, 3)
        if not mountd_port or not nfs_port:
            return {k: False for k in paths}

        exports = _mount_exports(nas_ip, mountd_port)
        exports = [_normalize_export(e) for e in exports]
        first   = next(iter(paths.values()))
        export  = next((e for e in sorted(exports, key=len, reverse=True)
                        if first.startswith(e)), None)
        if not export:
            return {k: False for k in paths}

        root_fh = _mount_mnt(nas_ip, mountd_port, export,
                              udp=(not mountd_tcp and bool(mountd_udp)))

        results = {}
        for key, path in paths.items():
            rel   = path[len(export):].lstrip("/")
            parts = [p for p in rel.split("/") if p]
            fh    = root_fh
            ok    = True
            for part in parts:
                child = _nfs_lookup(nas_ip, nfs_port, fh, part)
                if child is None:
                    try:
                        _nfs_mkdir(nas_ip, nfs_port, fh, part)
                        child = _nfs_lookup(nas_ip, nfs_port, fh, part)
                    except Exception:
                        pass
                if child is None:
                    ok = False
                    break
                fh = child
            results[key] = ok

        _mount_umnt(nas_ip, mountd_port, export)
        return results

    except Exception:
        return {k: False for k in paths}

def section_header(title, desc=None):
    pad = max(1, 38 - len(title))
    print(f"\n  {BLUE}── {title} {'─' * pad}{RESET}")
    if desc:
        print(f"  {SUBTEXT}{desc}{RESET}")
    print()

def detect_local_timezone():
    """Detect system timezone without third-party libraries."""
    try:
        link = os.path.realpath("/etc/localtime")
        for marker in ["/zoneinfo/", "\\zoneinfo\\"]:
            if marker in link:
                tz = link.split(marker)[-1]
                if tz in TIMEZONES_FLAT:
                    return tz
    except Exception:
        pass
    return "America/New_York"

def region_for_timezone(tz):
    """Return which region a timezone belongs to."""
    for region, tzs in TIMEZONES.items():
        if tz in tzs:
            return region
    return list(TIMEZONES.keys())[0]

# ── Wizard: General ───────────────────────────────────────────────────────────

def wizard_general(existing):
    section_header("General", "Basic system settings")

    detected_tz    = detect_local_timezone()
    default_tz     = existing.get("TZ", detected_tz)
    default_region = region_for_timezone(default_tz)

    region = questionary.select(
        "  Timezone — region:",
        choices=[Choice(r, value=r) for r in TIMEZONES.keys()],
        default=default_region,
        style=MOCHA,
    ).ask()

    if region is None:
        return None

    tz_default = default_tz if default_tz in TIMEZONES[region] else TIMEZONES[region][0]
    tz = questionary.select(
        "  Timezone:",
        choices=[Choice(t, value=t) for t in TIMEZONES[region]],
        default=tz_default,
        style=MOCHA,
    ).ask()

    puid = questionary.text(
        f"  User ID for file permissions [{existing.get('PUID', '1000')}]:",
        default=existing.get("PUID", "1000"),
        style=MOCHA,
    ).ask()

    pgid = questionary.text(
        f"  Group ID for file permissions [{existing.get('PGID', '1000')}]:",
        default=existing.get("PGID", "1000"),
        style=MOCHA,
    ).ask()

    return {
        "TZ":   tz   or default_tz,
        "PUID": puid or "1000",
        "PGID": pgid or "1000",
    }

# ── Wizard: Domain ────────────────────────────────────────────────────────────

def wizard_domain(existing):
    section_header("Base Domain")

    print(f"  {SUBTEXT}Nginx Proxy Manager uses your domain to route subdomains to services.{RESET}")
    print(f"  {SUBTEXT}Example:  jellyfin.{{your-domain}}  →  Jellyfin{RESET}")
    print(f"  {SUBTEXT}          immich.{{your-domain}}    →  Immich{RESET}\n")

    access = questionary.select(
        "  How will you access your services?",
        choices=[
            Choice("Local only (localhost)   — this machine only, no extra setup needed",   value="local"),
            Choice("Local network domain     — across your home network via local DNS",      value="lan"),
            Choice("Public domain            — accessible from anywhere on the internet",    value="public"),
        ],
        style=MOCHA,
    ).ask()

    if access is None:
        return existing.get("DOMAIN", "localhost")

    if access == "local":
        print(f"\n  {GREEN}✓ No extra setup needed.{RESET}")
        print(f"  {SUBTEXT}Access services directly at http://localhost:<port>{RESET}\n")
        return "localhost"

    elif access == "lan":
        print(f"\n  {BLUE}What you'll need:{RESET}")
        print(f"  {SUBTEXT}  1. A local domain name  (e.g. homelab.local){RESET}")
        print(f"  {SUBTEXT}  2. A DNS entry pointing it to this machine's IP{RESET}")
        print(f"  {SUBTEXT}     → AdGuard Home (in this stack) can handle this:{RESET}")
        print(f"  {SUBTEXT}       Settings → DNS rewrites → *.homelab.local → <your-IP>{RESET}\n")
        domain = questionary.text(
            "  Local domain:",
            default=existing.get("DOMAIN", "homelab.local"),
            style=MOCHA,
        ).ask()
        return domain or "homelab.local"

    else:  # public
        print(f"\n  {BLUE}What you'll need:{RESET}")
        print(f"  {SUBTEXT}  1. A registered domain  (Cloudflare, Namecheap, etc.){RESET}")
        print(f"  {SUBTEXT}  2. An A record pointing to your public IP address{RESET}")
        print(f"  {SUBTEXT}  3. Ports 80 and 443 forwarded to this machine{RESET}")
        print(f"  {SUBTEXT}  4. SSL certificates — Nginx Proxy Manager handles this{RESET}")
        print(f"  {SUBTEXT}     automatically via Let's Encrypt once configured.{RESET}\n")
        domain = questionary.text(
            "  Public domain:",
            default=existing.get("DOMAIN", "example.com"),
            style=MOCHA,
        ).ask()
        return domain or "example.com"

# ── Wizard: NAS / Storage ─────────────────────────────────────────────────────

def wizard_nas(existing):
    section_header("NAS / Storage", "Where your media, photos, and documents live")
    print(f"  {SUBTEXT}Services fall back to local Docker volumes if skipped.{RESET}\n")

    setup = questionary.confirm(
        "  Set up NAS/Network Storage?",
        default=True,
        style=MOCHA,
    ).ask()

    if not setup:
        return {k: existing.get(k, "") for k in SUBFOLDER_KEYS}

    # Device type
    print()
    device_key = questionary.select(
        "  Storage type:",
        choices=[Choice(v["name"], value=k) for k, v in NAS_DEVICES.items()],
        style=MOCHA,
    ).ask()

    if device_key is None:
        return {}

    device = NAS_DEVICES[device_key]

    # Show hint for the selected device
    print(f"  {SUBTEXT}{device['hint']}{RESET}")

    # NAS IP (not needed for local)
    nas_ip = existing.get("NAS_IP", "192.168.1.100")
    if device_key != "local":
        print()
        nas_ip = questionary.text(
            f"  NAS IP address:",
            default=nas_ip,
            style=MOCHA,
        ).ask() or nas_ip

        # Connectivity test
        print(f"  {SUBTEXT}Testing connectivity to {nas_ip}...{RESET}", end="", flush=True)
        ping_cmd = ["ping", "-c", "1", "-W", "2", nas_ip] if os.name != "nt" \
                   else ["ping", "-n", "1", "-w", "2000", nas_ip]
        result = subprocess.run(ping_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print(f"\r  {GREEN}✓ Reachable: {nas_ip}{RESET}                        ")
        else:
            print(f"\r  {YELLOW}⚠  Could not reach {nas_ip} — check IP and network.{RESET}")
            proceed = questionary.confirm(
                "  Continue anyway?",
                default=False,
                style=MOCHA,
            ).ask()
            if not proceed:
                return {}

    # Base path — browse NFS interactively for NFS-capable devices, text input otherwise
    nfs_capable = device_key in ("unifi", "nfs", "truenas", "synology", "qnap")
    base = None

    if nfs_capable and device_key != "local":
        print(f"\n  {SUBTEXT}Connecting to NFS on {nas_ip}...{RESET}", end="", flush=True)
        try:
            _portmap_getport(nas_ip, 100005, 3)
            can_browse = True
        except Exception:
            can_browse = False

        if can_browse:
            print(f"\r  {GREEN}✓ NFS available — browse to select your base folder{RESET}          ")
            base = browse_nfs(nas_ip)
        else:
            print(f"\r  {YELLOW}⚠  NFS not reachable — running diagnostics...{RESET}               ")
            diagnose_nfs(nas_ip)
            print(f"  {SUBTEXT}You can still enter the path manually below.{RESET}")

    if base is None:
        # Fallback: manual text input
        existing_media = existing.get("NAS_MEDIA_PATH", "")
        guessed_base = ""
        if existing_media and existing_media not in ("/volume1/media", ""):
            parts = existing_media.rstrip("/").split("/")
            if len(parts) > 1:
                guessed_base = "/".join(parts[:-1])
        default_base = guessed_base or device["example"]

        print()
        if device.get("template"):
            print(f"  {SURFACE}Template: {device['template']}{RESET}")
        base = questionary.text(
            "  Base storage path:",
            default=default_base,
            style=MOCHA,
        ).ask() or default_base

    base = base.rstrip("/")

    # Derive subfolder paths
    paths = {key: f"{base}/{sub}" for key, sub in SUBFOLDER_KEYS.items()}

    # Offer to customize individual paths
    print()
    customize = questionary.confirm(
        "  Customize individual subfolder paths?",
        default=False,
        style=MOCHA,
    ).ask()

    if customize:
        print()
        for key in paths:
            label = SUBFOLDER_KEYS[key].capitalize()
            val = questionary.text(
                f"  {label}:",
                default=paths[key],
                style=MOCHA,
            ).ask()
            if val:
                paths[key] = val

    # Show paths — for local devices check existence and offer to create;
    # for remote devices the paths live on the NAS so we just display them.
    print(f"\n  {BLUE}Paths{RESET}")
    if device_key == "local":
        missing_paths = []
        for key, path in paths.items():
            label = SUBFOLDER_KEYS[key].capitalize()
            if os.path.isdir(path):
                print(f"  {GREEN}✓{RESET}  {SUBTEXT}{label:<12}{RESET}{TEXT}{path}{RESET}")
            else:
                print(f"  {YELLOW}✗{RESET}  {SUBTEXT}{label:<12}{RESET}{SUBTEXT}{path}{RESET}")
                missing_paths.append((label, path))

        if missing_paths:
            print()
            create = questionary.confirm(
                f"  Create {len(missing_paths)} missing subfolder(s)?",
                default=True,
                style=MOCHA,
            ).ask()
            if create:
                print()
                for label, path in missing_paths:
                    try:
                        os.makedirs(path, exist_ok=True)
                        print(f"  {GREEN}✓ Created:{RESET}  {TEXT}{path}{RESET}")
                    except OSError as e:
                        print(f"  {RED}✗ Failed:{RESET}   {SUBTEXT}{path} — {e}{RESET}")
    else:
        nfs_capable = device_key in ("unifi", "nfs", "truenas", "synology", "qnap")
        nfs_results = None

        if nfs_capable:
            print(f"  {SUBTEXT}Checking paths on NAS...{RESET}", end="", flush=True)
            nfs_results = check_nfs_paths(nas_ip, paths)
            # Clear the checking line
            print(f"\r{' ' * 40}\r", end="", flush=True)

        if nfs_results is not None:
            missing_remote = []
            for key, path in paths.items():
                label = SUBFOLDER_KEYS[key].capitalize()
                if nfs_results.get(key):
                    print(f"  {GREEN}✓{RESET}  {SUBTEXT}{label:<12}{RESET}{TEXT}{path}{RESET}")
                else:
                    print(f"  {YELLOW}✗{RESET}  {SUBTEXT}{label:<12}{RESET}{SUBTEXT}{path}{RESET}")
                    missing_remote.append((label, path))
            if missing_remote:
                print(f"\n  {YELLOW}⚠  {len(missing_remote)} folder(s) not found on NAS.{RESET}")
                action = questionary.select(
                    "  What would you like to do?",
                    choices=[
                        Choice("Create them now (via NFS)", value="auto"),
                        Choice("I'll create them manually",  value="manual"),
                    ],
                    style=MOCHA,
                ).ask()

                if action == "auto":
                    missing_paths = {k: p for k, p in paths.items()
                                     if not nfs_results.get(k)}
                    print(f"  {SUBTEXT}Creating folders...{RESET}", end="", flush=True)
                    created = create_nfs_paths(nas_ip, missing_paths)
                    print(f"\r{' ' * 30}\r", end="", flush=True)
                    for key, path in missing_paths.items():
                        label = SUBFOLDER_KEYS[key].capitalize()
                        if created.get(key):
                            print(f"  {GREEN}✓{RESET}  {SUBTEXT}{label:<12}{RESET}{TEXT}{path}{RESET}")
                        else:
                            print(f"  {RED}✗{RESET}  {SUBTEXT}{label:<12}{RESET}{SUBTEXT}{path} — could not create{RESET}")
                else:
                    print(f"  {SUBTEXT}Create these folders on your NAS before starting containers.{RESET}")
            else:
                print(f"\n  {GREEN}✓ All paths verified on NAS.{RESET}")
        else:
            for key, path in paths.items():
                label = SUBFOLDER_KEYS[key].capitalize()
                print(f"  {SUBTEXT}  {label:<12}{RESET}{TEXT}{path}{RESET}")
            print(f"\n  {SUBTEXT}Ensure these folders exist on your NAS before starting containers.{RESET}")

    return {"NAS_IP": nas_ip, **paths}

def _write_immich_gpu_override(suffix):
    """
    Write (or remove) immich/docker-compose.override.yml with the GPU
    device reservation block. Only NVIDIA CUDA needs this; other
    accelerators work via the image tag alone.
    """
    override_path = os.path.join(SCRIPT_DIR, "immich", "docker-compose.override.yml")
    if suffix == "-cuda":
        content = (
            "# Auto-generated by deploy.py — NVIDIA GPU reservation for Immich ML\n"
            "services:\n"
            "  immich-machine-learning:\n"
            "    deploy:\n"
            "      resources:\n"
            "        reservations:\n"
            "          devices:\n"
            "            - driver: nvidia\n"
            "              count: 1\n"
            "              capabilities: [gpu]\n"
        )
        with open(override_path, "w") as f:
            f.write(content)
    else:
        if os.path.exists(override_path):
            os.remove(override_path)

def wizard_immich(existing):
    section_header("Immich", "Photo management & ML acceleration")

    choices = [
        Choice("CPU         — works everywhere, no GPU needed",  value=""),
        Choice("NVIDIA CUDA — fastest, requires NVIDIA GPU",     value="-cuda"),
        Choice("ARM NN      — ARM Mali GPU (e.g. Raspberry Pi)", value="-armnn"),
        Choice("AMD ROCm    — AMD GPU",                          value="-rocm"),
        Choice("Intel       — Intel GPU / iGPU (OpenVINO)",      value="-openvino"),
    ]
    current = existing.get("IMMICH_ML_TAG_SUFFIX", "")
    default = next((c for c in choices if c.value == current), choices[0])

    suffix = questionary.select(
        "  Immich ML accelerator:",
        choices=choices,
        default=default,
        style=MOCHA,
    ).ask()
    if suffix is None:
        return None

    _write_immich_gpu_override(suffix)

    if suffix == "-cuda":
        print(f"  {SUBTEXT}NVIDIA override written — ensure NVIDIA Container Toolkit is installed.{RESET}\n")
    elif suffix:
        print(f"  {SUBTEXT}Image suffix {suffix} will be used — no extra config required.{RESET}\n")
    else:
        print(f"  {SUBTEXT}CPU mode — no GPU required.{RESET}\n")

    return {
        "IMMICH_VERSION":        existing.get("IMMICH_VERSION", "release"),
        "IMMICH_UPLOAD_LOCATION": existing.get("IMMICH_UPLOAD_LOCATION", "./library"),
        "IMMICH_ML_TAG_SUFFIX":  suffix,
    }

# ── Setup wizard (orchestrates all wizard sections) ───────────────────────────

def run_setup(existing=None):
    existing = existing or {}
    values = dict(existing)

    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Setup Wizard{RESET}\n")
    print(f"  {SUBTEXT}Press Enter to accept defaults. Ctrl+C to cancel at any time.{RESET}\n")

    # Custom wizard sections
    result = wizard_general(existing)
    if result is None:
        return None
    values.update(result)

    domain = wizard_domain(existing)
    if domain is None:
        return None
    values["DOMAIN"] = domain

    nas = wizard_nas(existing)
    if nas is None:
        return None
    values.update(nas)

    immich = wizard_immich(existing)
    if immich is None:
        return None
    values.update(immich)

    # Generic sections: AdGuard, Passwords, Homepage API keys
    for section in ENV_SECTIONS:
        section_header(section["name"], section.get("desc"))

        if section.get("optional"):
            skip = questionary.confirm(
                f"  Skip {section['name']}?",
                default=False,
                style=MOCHA,
            ).ask()
            if skip:
                print()
                continue

        if section.get("bulk_password"):
            gen = questionary.select(
                "  How do you want to set passwords?",
                choices=[
                    Choice("Generate random passwords  — recommended",         value="generate"),
                    Choice("Use defaults               — all set to changeme", value="defaults"),
                    Choice("Set individually           — configure each one",  value="individual"),
                ],
                style=MOCHA,
            ).ask()

            if gen == "generate":
                for var in section["vars"]:
                    if var.get("password"):
                        values[var["key"]] = gen_password()
                    else:
                        values[var["key"]] = existing.get(var["key"], var["default"])
                print(f"  {GREEN}✓ Random passwords generated.{RESET}\n")
                continue
            elif gen == "defaults":
                for var in section["vars"]:
                    values[var["key"]] = var["default"]
                print(f"  {YELLOW}⚠  Using default passwords — change before exposing to the internet.{RESET}\n")
                continue

        for var in section["vars"]:
            current = existing.get(var["key"], var["default"])
            display  = "****" if (var.get("password") and current not in ("", "changeme")) else current
            prompt   = f"  {var['desc']}"
            if display:
                prompt += f" [{display}]"
            answer = questionary.text(prompt, default=current, style=MOCHA).ask()
            if answer is None:
                return None
            values[var["key"]] = answer if answer.strip() else current

        print()

    return values

def setup_first_run():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Deploy Tool{RESET}")
    print(f"  {SURFACE}{'─' * 40}{RESET}\n")
    print(f"  {YELLOW}⚠  No .env file found.{RESET}")
    print(f"  {SUBTEXT}This is required before deploying anything.{RESET}\n")

    choice = questionary.select(
        "How would you like to configure your environment?",
        choices=[
            Choice("Use defaults       — spin up instantly with changeme passwords", value="defaults"),
            Choice("Guided setup       — walk through each setting interactively",   value="wizard"),
        ],
        style=MOCHA,
    ).ask()

    if choice is None:
        return False

    if choice == "defaults":
        shutil.copy(ENV_EXAMPLE, ENV_FILE)
        print(f"\n  {GREEN}✓ .env created from defaults.{RESET}")
        print(f"  {SUBTEXT}Edit .env any time to change passwords or NAS paths.{RESET}\n")
    else:
        values = run_setup()
        if values is None:
            return False
        save_env(values)
        print(f"\n  {GREEN}✓ .env saved.{RESET}\n")

    return True

# ── Deploy helpers ────────────────────────────────────────────────────────────

def all_optional_services():
    return [svc for cat in CATEGORIES for svc in cat["services"]]

def find_service(svc_id):
    return next((s for s in all_optional_services() if s["id"] == svc_id), None)

def resolve_dependencies(selected_ids):
    resolved = set(selected_ids)
    changed = True
    while changed:
        changed = False
        for svc in all_optional_services():
            if svc["id"] in resolved:
                for req in svc.get("requires", []):
                    if req not in resolved:
                        resolved.add(req)
                        changed = True
    return resolved

def get_service_images(profiles):
    """
    Return {service_name: image} for the given profiles by parsing
    'docker compose config --format json' (falls back to YAML grep).
    """
    import json as _json
    flags = " ".join(f"--profile {p}" for p in profiles) if profiles else ""
    # Try JSON format first (Docker Compose ≥ 2.15)
    r = subprocess.run(
        f"docker compose {flags} config --format json",
        shell=True, cwd=SCRIPT_DIR, capture_output=True, text=True,
    )
    if r.returncode == 0:
        try:
            cfg = _json.loads(r.stdout)
            return {
                name: svc.get("image", "")
                for name, svc in cfg.get("services", {}).items()
                if svc.get("image")
            }
        except Exception:
            pass
    # Fallback: parse YAML output line by line
    r = subprocess.run(
        f"docker compose {flags} config",
        shell=True, cwd=SCRIPT_DIR, capture_output=True, text=True,
    )
    images, current = {}, None
    for line in r.stdout.splitlines():
        m = re.match(r"^  ([a-zA-Z0-9_-]+):$", line)
        if m:
            current = m.group(1)
        elif current:
            m2 = re.match(r"^    image:\s+(.+)$", line)
            if m2:
                images[current] = m2.group(1).strip()
    return images

def print_images(profiles):
    """Print a table of service → image for the given profiles."""
    images = get_service_images(profiles)
    if not images:
        print(f"\n  {YELLOW}Could not resolve images (is Docker running?){RESET}\n")
        return
    col = max(len(s) for s in images) + 2
    print(f"\n  {BLUE}◆ Docker images{RESET}")
    print(f"  {SURFACE}{'─' * (col + 52)}{RESET}\n")
    for svc, img in sorted(images.items()):
        print(f"  {SUBTEXT}{svc:<{col}}{RESET}{TEXT}{img}{RESET}")
    print()

def build_command(profiles, pull=True):
    flags = " ".join(f"--profile {p}" for p in profiles) if profiles else ""
    pull_flag = "" if pull else " --pull never"
    return f"docker compose {flags} up -d{pull_flag}".strip()

def pull_images_sequentially(profiles):
    """
    Pull one image at a time with a short pause between each to avoid
    Docker Hub unauthenticated rate limits (100 pulls / 6 hr per IP).
    """
    import time as _t
    flags = " ".join(f"--profile {p}" for p in profiles) if profiles else ""
    result = subprocess.run(
        f"docker compose {flags} config --services",
        shell=True, cwd=SCRIPT_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False

    services = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
    if not services:
        return False

    images = get_service_images(profiles)
    col    = max((len(s) for s in services), default=16) + 2

    print(f"\n  {BLUE}◆ Pulling {len(services)} images (sequential){RESET}\n")
    failed = []
    for i, svc in enumerate(services, 1):
        img_hint = f"  {SUBTEXT}{images.get(svc, '')}{RESET}" if svc in images else ""
        print(f"  {SUBTEXT}[{i}/{len(services)}]{RESET}  {TEXT}{svc:<{col}}{RESET}{img_hint}", flush=True)
        r = subprocess.run(
            f"docker compose {flags} pull {svc}",
            shell=True, cwd=SCRIPT_DIR,
        )
        if r.returncode != 0:
            failed.append(svc)
        if i < len(services):
            _t.sleep(1)

    if failed:
        print(f"\n  {YELLOW}⚠  Pull failed for: {', '.join(failed)}{RESET}")
    print()

def print_summary(selected_ids, profiles):
    print()
    print(f"  {BLUE}◆ Deployment Summary{RESET}")
    print(f"  {SURFACE}{'─' * 40}{RESET}")
    print(f"  {SUBTEXT}Core:  {', '.join(s['name'] for s in CORE)}{RESET}")
    if selected_ids:
        svcs  = all_optional_services()
        names = [s["name"] for s in svcs if s["id"] in selected_ids]
        line, lines = "", []
        for name in names:
            if len(line) + len(name) > 58:
                lines.append(line.rstrip(", "))
                line = ""
            line += name + ", "
        if line:
            lines.append(line.rstrip(", "))
        print(f"  {SUBTEXT}Apps:  {lines[0]}{RESET}")
        for l in lines[1:]:
            print(f"         {SUBTEXT}{l}{RESET}")
    else:
        print(f"  {SUBTEXT}Apps:  (none){RESET}")

    # Images table
    images = get_service_images(profiles)
    if images:
        col = max(len(s) for s in images) + 2
        print(f"\n  {SUBTEXT}{'Service':<{col}}Image{RESET}")
        print(f"  {SURFACE}{'─' * (col + 50)}{RESET}")
        for svc, img in sorted(images.items()):
            print(f"  {TEXT}{svc:<{col}}{RESET}{SUBTEXT}{img}{RESET}")

    print()
    print(f"  {MAUVE}Command:{RESET}  {TEXT}{build_command(profiles)}{RESET}")
    print()

# ── Access URL summary ────────────────────────────────────────────────────────

def print_access_urls(selected_ids):
    all_svcs  = {s["id"]: s for s in all_optional_services()}
    core_svcs = CORE

    print(f"\n  {BLUE}◆ Services are up — access them at:{RESET}")
    print(f"  {SURFACE}{'─' * 44}{RESET}\n")

    # Core services (always shown)
    for svc in core_svcs:
        url  = f"http://localhost:{svc['port']}"
        name = svc["name"]
        desc = svc["desc"]
        pad  = max(1, 22 - len(name))
        print(f"  {TEXT}{name}{' ' * pad}{RESET}{SUBTEXT}{desc:<28}{RESET}  {MAUVE}{url}{RESET}")

    # Optional services that were deployed
    deployed = [all_svcs[sid] for sid in selected_ids if sid in all_svcs and "port" in all_svcs[sid]]
    if deployed:
        print(f"  {SURFACE}{'─' * 44}{RESET}")
        for svc in deployed:
            url  = f"http://localhost:{svc['port']}"
            name = svc["name"]
            desc = svc["desc"]
            pad  = max(1, 22 - len(name))
            print(f"  {TEXT}{name}{' ' * pad}{RESET}{SUBTEXT}{desc:<28}{RESET}  {MAUVE}{url}{RESET}")

    print(f"\n  {SUBTEXT}Tip: Nginx Proxy Manager (port 81) lets you set up{RESET}")
    print(f"  {SUBTEXT}     subdomain routing and SSL once services are running.{RESET}\n")

# ── Service selection ─────────────────────────────────────────────────────────

def select_by_category():
    choices = [
        Choice(f"{cat['name']}  — {cat['desc']}", value=cat["id"])
        for cat in CATEGORIES
    ]
    selected_cats = questionary.checkbox(
        "Select categories to deploy:",
        choices=choices,
        style=MOCHA,
        instruction="(space to select, enter to confirm)"
    ).ask()
    if selected_cats is None:
        return None, set()
    selected_ids = set()
    for cat in CATEGORIES:
        if cat["id"] in selected_cats:
            for svc in cat["services"]:
                selected_ids.add(svc["id"])
    return selected_cats, selected_ids

def select_individually():
    choices = []
    for cat in CATEGORIES:
        choices.append(Separator(f"── {cat['name']}"))
        for svc in cat["services"]:
            req_note = f"  [requires: {', '.join(svc['requires'])}]" if svc.get("requires") else ""
            choices.append(Choice(
                f"{svc['name']}  — {svc['desc']}{req_note}",
                value=svc["id"]
            ))
    selected = questionary.checkbox(
        "Select services to deploy:",
        choices=choices,
        style=MOCHA,
        instruction="(space to select, enter to confirm)"
    ).ask()
    if selected is None:
        return None, set()
    selected_ids = set(selected)
    resolved     = resolve_dependencies(selected_ids)
    auto_added   = resolved - selected_ids
    if auto_added:
        names = [find_service(sid)["name"] for sid in auto_added if find_service(sid)]
        print(f"\n  {YELLOW}⚠  Auto-adding required dependencies: {', '.join(names)}{RESET}")
    return list(resolved), resolved

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(ENV_FILE):
        ok = setup_first_run()
        if not ok:
            print(f"\n  {SUBTEXT}Setup cancelled.{RESET}\n")
            return

    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Deploy Tool{RESET}")
    print(f"  {SURFACE}{'─' * 40}{RESET}\n")
    print(f"  {GREEN}✓ Core (always deployed):{RESET}")
    for svc in CORE:
        print(f"    {SUBTEXT}{svc['name']}{RESET}  {SURFACE}—  {svc['desc']}{RESET}")
    print()

    mode = questionary.select(
        "How would you like to select services?",
        choices=[
            Choice("By category        — deploy entire groups at once", value="category"),
            Choice("Individual         — pick specific services",        value="individual"),
            Choice("Deploy everything  — bring the full stack up",       value="all"),
            Choice("Core only          — proxy + DNS only",              value="core"),
            Separator(),
            Choice("List images        — show all Docker images in use", value="images"),
            Choice("Reconfigure .env   — re-run setup wizard",           value="reconfigure"),
        ],
        style=MOCHA,
    ).ask()

    if mode is None:
        return

    if mode == "reconfigure":
        existing = load_env()
        values   = run_setup(existing)
        if values:
            save_env(values)
            print(f"\n  {GREEN}✓ .env updated.{RESET}\n")
        return

    if mode == "images":
        print_images(["all"])
        questionary.press_any_key_to_continue("  Press any key to go back...").ask()
        main()
        return

    selected_ids, profiles = set(), []

    if mode == "all":
        selected_ids = {svc["id"] for svc in all_optional_services()}
        profiles     = ["all"]
    elif mode == "core":
        selected_ids, profiles = set(), []
    elif mode == "category":
        profiles, selected_ids = select_by_category()
        if profiles is None:
            return
    elif mode == "individual":
        profiles, selected_ids = select_individually()
        if profiles is None:
            return

    print_summary(selected_ids, profiles)

    confirm = questionary.confirm("Deploy now?", default=True, style=MOCHA).ask()
    if confirm:
        pull_images_sequentially(profiles)
        cmd = build_command(profiles, pull=False)
        print(f"  {GREEN}▶ Starting containers:{RESET} {TEXT}{cmd}{RESET}\n")
        result = subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)
        if result.returncode == 0:
            print(f"\n  {GREEN}✓ Done.{RESET}")
            print_access_urls(selected_ids)
        else:
            print(f"\n  {RED}✗ Something went wrong. Check the output above.{RESET}\n")
    else:
        print(f"\n  {SUBTEXT}Run manually:{RESET}  {TEXT}{build_command(profiles)}{RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {SUBTEXT}Cancelled.{RESET}\n")
