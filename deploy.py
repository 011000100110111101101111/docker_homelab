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
        nas_ip = questionary.text(
            f"\n  NAS IP address [{nas_ip}]:",
            default=nas_ip,
            style=MOCHA,
        ).ask() or nas_ip

    # Guess base path from existing config
    existing_media = existing.get("NAS_MEDIA_PATH", "")
    guessed_base = ""
    if existing_media and existing_media not in ("/volume1/media", ""):
        parts = existing_media.rstrip("/").split("/")
        if len(parts) > 1:
            guessed_base = "/".join(parts[:-1])
    default_base = guessed_base or device["example"]

    # Show path template hint if the device has one
    print()
    if device.get("template"):
        print(f"  {SURFACE}Template: {device['template']}{RESET}")

    base = questionary.text(
        f"  Base storage path [{default_base}]:",
        default=default_base,
        style=MOCHA,
    ).ask() or default_base

    base = base.rstrip("/")

    # Derive subfolder paths
    paths = {key: f"{base}/{sub}" for key, sub in SUBFOLDER_KEYS.items()}

    # Show derived paths
    print(f"\n  {BLUE}Derived paths:{RESET}")
    for key, path in paths.items():
        label = SUBFOLDER_KEYS[key].capitalize()
        print(f"    {SUBTEXT}{label:<12}{RESET} {TEXT}{path}{RESET}")

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
                f"  {label} [{paths[key]}]:",
                default=paths[key],
                style=MOCHA,
            ).ask()
            if val:
                paths[key] = val

    return {"NAS_IP": nas_ip, **paths}

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

def build_command(profiles):
    if not profiles:
        return "docker compose up -d"
    flags = " ".join(f"--profile {p}" for p in profiles)
    return f"docker compose {flags} up -d"

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
        cmd = build_command(profiles)
        print(f"\n  {GREEN}▶ Running:{RESET} {TEXT}{cmd}{RESET}\n")
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
