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

# ── Venv bootstrap ───────────────────────────────────────────────────────────
# On first run, creates a .venv in the project directory, installs dependencies,
# and re-executes itself inside the venv — fully transparent to the user.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR   = os.path.join(SCRIPT_DIR, ".venv")
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

# ── Dependencies (guaranteed available inside venv) ──────────────────────────

import questionary
from questionary import Style, Choice, Separator

# ── Catppuccin Mocha style ───────────────────────────────────────────────────

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

def c(color, text): return f"{color}{text}{RESET}"

# ── .env variable definitions ─────────────────────────────────────────────────
#
# Each section has a name, description, and list of variables.
# required=True  → shown in guided setup
# required=False → shown but skippable / optional
# password=True  → can be bulk-generated
# secret=True    → masked input

ENV_SECTIONS = [
    {
        "name": "General",
        "desc": "Basic system settings",
        "vars": [
            {"key": "TZ",     "desc": "Timezone",                               "default": "America/New_York"},
            {"key": "PUID",   "desc": "User ID for file permissions",            "default": "1000"},
            {"key": "PGID",   "desc": "Group ID for file permissions",           "default": "1000"},
            {"key": "DOMAIN", "desc": "Base domain (e.g. homelab.local)",        "default": "localhost"},
        ],
    },
    {
        "name": "NAS / Storage",
        "desc": "Network storage — skip if you have no NAS",
        "optional": True,
        "vars": [
            {"key": "NAS_IP",            "desc": "NAS IP address",           "default": "192.168.1.100"},
            {"key": "NAS_MEDIA_PATH",    "desc": "Path to media on NAS",     "default": "/volume1/media"},
            {"key": "NAS_MUSIC_PATH",    "desc": "Path to music on NAS",     "default": "/volume1/music"},
            {"key": "NAS_BOOKS_PATH",    "desc": "Path to books on NAS",     "default": "/volume1/books"},
            {"key": "NAS_DOWNLOADS_PATH","desc": "Path to downloads on NAS", "default": "/volume1/downloads"},
            {"key": "NAS_PHOTOS_PATH",   "desc": "Path to photos on NAS",    "default": "/volume1/photos"},
            {"key": "NAS_DOCUMENTS_PATH","desc": "Path to documents on NAS", "default": "/volume1/documents"},
        ],
    },
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
            {"key": "MEALIE_DB_PASSWORD",    "desc": "Mealie database password",       "default": "changeme", "password": True},
            {"key": "MEALIE_SECRET_KEY",     "desc": "Mealie secret key",              "default": "changeme", "password": True},
            {"key": "PAPERLESS_DB_PASSWORD", "desc": "Paperless database password",    "default": "changeme", "password": True},
            {"key": "PAPERLESS_SECRET_KEY",  "desc": "Paperless secret key",           "default": "changeme", "password": True},
            {"key": "PAPERLESS_ADMIN_USER",  "desc": "Paperless admin username",       "default": "admin"},
            {"key": "PAPERLESS_ADMIN_PASSWORD","desc": "Paperless admin password",     "default": "changeme", "password": True},
            {"key": "IMMICH_DB_PASSWORD",    "desc": "Immich database password",       "default": "changeme", "password": True},
            {"key": "IMMICH_DB_USERNAME",    "desc": "Immich database username",       "default": "immich"},
            {"key": "IMMICH_DB_NAME",        "desc": "Immich database name",           "default": "immich"},
            {"key": "N8N_ENCRYPTION_KEY",    "desc": "n8n encryption key",             "default": "changeme", "password": True},
            {"key": "KOEL_DB_PASSWORD",      "desc": "Koel database password",         "default": "changeme", "password": True},
            {"key": "METABASE_DB_PASSWORD",  "desc": "Metabase database password",     "default": "changeme", "password": True},
            {"key": "PASTEFY_DB_PASSWORD",   "desc": "Pastefy database password",      "default": "changeme", "password": True},
            {"key": "NOCODB_DB_PASSWORD",    "desc": "NocoDB database password",       "default": "changeme", "password": True},
        ],
    },
    {
        "name": "Homepage API Keys",
        "desc": "Optional — fill in after services are running to enable dashboard widgets",
        "optional": True,
        "vars": [
            {"key": "HOMEPAGE_VAR_JELLYFIN",        "desc": "Jellyfin API key",      "default": ""},
            {"key": "HOMEPAGE_VAR_JELLYSEER",       "desc": "Jellyseer API key",     "default": ""},
            {"key": "HOMEPAGE_VAR_ADGUARD_USERNAME","desc": "AdGuard username",      "default": "admin"},
            {"key": "HOMEPAGE_VAR_ADGUARD_PASSWORD","desc": "AdGuard password",      "default": "changeme"},
            {"key": "HOMEPAGE_VAR_PORTAINER_KEY",   "desc": "Portainer API key",     "default": ""},
        ],
    },
]

# ── Service definitions ───────────────────────────────────────────────────────

CORE = [
    {"id": "nginx-proxy-manager", "name": "Nginx Proxy Manager", "desc": "Reverse proxy & SSL termination"},
    {"id": "adguard",             "name": "AdGuard Home",         "desc": "DNS & ad blocking"},
]

CATEGORIES = [
    {
        "id": "media",
        "name": "Media",
        "desc": "Streaming and music",
        "services": [
            {"id": "jellyfin",  "name": "Jellyfin",  "desc": "Media server"},
            {"id": "jellyseer", "name": "Jellyseer", "desc": "Media requests", "requires": ["jellyfin"]},
            {"id": "koel",      "name": "Koel",       "desc": "Music streaming"},
        ],
    },
    {
        "id": "photos",
        "name": "Photos",
        "desc": "Photo backup and management",
        "services": [
            {"id": "immich", "name": "Immich", "desc": "Photo management & ML search"},
        ],
    },
    {
        "id": "productivity",
        "name": "Productivity",
        "desc": "Recipes, documents, and automation",
        "services": [
            {"id": "mealie",        "name": "Mealie",        "desc": "Recipe manager"},
            {"id": "paperless-ngx", "name": "Paperless-NGX", "desc": "Document management"},
            {"id": "n8n",           "name": "n8n",           "desc": "Workflow automation"},
        ],
    },
    {
        "id": "dashboard",
        "name": "Dashboards",
        "desc": "Service overview and content feeds",
        "services": [
            {"id": "homepage", "name": "Homepage", "desc": "Service dashboard"},
            {"id": "glance",   "name": "Glance",   "desc": "News & content dashboard"},
        ],
    },
    {
        "id": "books",
        "name": "Books",
        "desc": "Reading and book management",
        "services": [
            {"id": "kavita",      "name": "Kavita",      "desc": "Book reader"},
            {"id": "calibre-web", "name": "Calibre Web", "desc": "Book processing & library"},
        ],
    },
    {
        "id": "dev",
        "name": "Dev Tools",
        "desc": "Databases, analytics, and utilities",
        "services": [
            {"id": "nocodb",    "name": "NocoDB",    "desc": "No-code database UI"},
            {"id": "metabase",  "name": "Metabase",  "desc": "Analytics & BI"},
            {"id": "pastefy",   "name": "Pastefy",   "desc": "Paste service"},
            {"id": "bytestash", "name": "Bytestash", "desc": "Code snippet manager"},
        ],
    },
]

# ── .env helpers ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE     = os.path.join(SCRIPT_DIR, ".env")
ENV_EXAMPLE  = os.path.join(SCRIPT_DIR, ".env.example")

def load_env():
    """Parse .env into a dict."""
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
    """Write values dict back to .env, preserving comments from .env.example."""
    if not os.path.exists(ENV_EXAMPLE):
        # Fallback: plain write
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
    """Generate a URL-safe random password."""
    return secrets.token_urlsafe(length)

# ── Setup wizard ──────────────────────────────────────────────────────────────

def run_setup(existing=None):
    """Interactive guided .env configuration."""
    existing = existing or {}
    values = dict(existing)

    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Setup Wizard{RESET}\n")
    print(f"  {SUBTEXT}Press Enter to accept the default value shown in brackets.{RESET}")
    print(f"  {SUBTEXT}Optional sections can be skipped entirely.{RESET}\n")

    for section in ENV_SECTIONS:
        print(f"  {BLUE}── {section['name']} {SURFACE}{'─' * (38 - len(section['name']))}{RESET}")
        print(f"  {SUBTEXT}{section['desc']}{RESET}\n")

        # Optional section — offer to skip
        if section.get("optional"):
            skip = questionary.confirm(
                f"  Skip {section['name']}?",
                default=False,
                style=MOCHA,
            ).ask()
            if skip:
                print()
                continue

        # Bulk password generation
        if section.get("bulk_password"):
            gen = questionary.select(
                "  How do you want to set passwords?",
                choices=[
                    Choice(f"{c(TEXT, 'Generate random passwords')}  {SUBTEXT}recommended{RESET}", value="generate"),
                    Choice(f"{c(TEXT, 'Use defaults')}               {SUBTEXT}all set to changeme{RESET}", value="defaults"),
                    Choice(f"{c(TEXT, 'Set individually')}           {SUBTEXT}configure each one{RESET}", value="individual"),
                ],
                style=MOCHA,
            ).ask()

            if gen == "generate":
                for var in section["vars"]:
                    if var.get("password"):
                        values[var["key"]] = gen_password()
                    else:
                        current = existing.get(var["key"], var["default"])
                        values[var["key"]] = current
                print(f"  {GREEN}✓ Random passwords generated.{RESET}\n")
                continue
            elif gen == "defaults":
                for var in section["vars"]:
                    values[var["key"]] = var["default"]
                print(f"  {YELLOW}⚠  Using default passwords — change these before exposing to the internet.{RESET}\n")
                continue
            # else fall through to individual

        # Individual variable prompts
        for var in section["vars"]:
            current = existing.get(var["key"], var["default"])
            display_default = "****" if (var.get("password") and current not in ("", "changeme")) else current
            prompt = f"  {var['desc']}"
            if display_default:
                prompt += f" [{c(SUBTEXT, display_default)}]"

            answer = questionary.text(
                prompt,
                default=current,
                style=MOCHA,
            ).ask()

            if answer is None:
                return None  # user ctrl-c'd

            values[var["key"]] = answer if answer.strip() else current

        print()

    return values

def setup_first_run():
    """Handle first-run env setup — offer defaults or guided wizard."""
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Deploy Tool{RESET}")
    print(f"  {SURFACE}{'─' * 40}{RESET}\n")
    print(f"  {YELLOW}⚠  No .env file found.{RESET}")
    print(f"  {SUBTEXT}This is required before deploying anything.{RESET}\n")

    choice = questionary.select(
        "How would you like to configure your environment?",
        choices=[
            Choice(f"{c(TEXT, 'Use defaults')}       {SUBTEXT}spin up instantly with changeme passwords{RESET}", value="defaults"),
            Choice(f"{c(TEXT, 'Guided setup')}       {SUBTEXT}walk through each setting interactively{RESET}", value="wizard"),
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
        svcs = all_optional_services()
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
    cmd = build_command(profiles)
    print(f"  {MAUVE}Command:{RESET}  {TEXT}{cmd}{RESET}")
    print()

# ── Service selection ─────────────────────────────────────────────────────────

def select_by_category():
    choices = [
        Choice(
            f"{c(TEXT, cat['name'])}  {SUBTEXT}{cat['desc']}{RESET}",
            value=cat["id"]
        )
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
        choices.append(Separator(f"  {MAUVE}── {cat['name']} {SURFACE}{'─' * (28 - len(cat['name']))}{RESET}"))
        for svc in cat["services"]:
            req_note = f"  {YELLOW}[requires: {', '.join(svc['requires'])}]{RESET}" if svc.get("requires") else ""
            choices.append(Choice(
                f"{c(TEXT, svc['name'])}  {SUBTEXT}{svc['desc']}{RESET}{req_note}",
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
    resolved = resolve_dependencies(selected_ids)
    auto_added = resolved - selected_ids
    if auto_added:
        names = [find_service(sid)["name"] for sid in auto_added if find_service(sid)]
        print(f"\n  {YELLOW}⚠  Auto-adding required dependencies: {', '.join(names)}{RESET}")

    return list(resolved), resolved

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Step 1: ensure .env exists
    if not os.path.exists(ENV_FILE):
        ok = setup_first_run()
        if not ok:
            print(f"\n  {SUBTEXT}Setup cancelled.{RESET}\n")
            return

    # Step 2: service selection
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {MAUVE}◆ Homelab Deploy Tool{RESET}")
    print(f"  {SURFACE}{'─' * 40}{RESET}\n")
    print(f"  {c(GREEN, '✓')} {c(SUBTEXT, 'Core (always deployed):')}")
    for svc in CORE:
        print(f"    {SUBTEXT}{svc['name']}{RESET}  {SURFACE}—  {svc['desc']}{RESET}")
    print()

    mode = questionary.select(
        "How would you like to select services?",
        choices=[
            Choice(f"{c(TEXT, 'By category')}       {SUBTEXT}deploy entire groups at once{RESET}",   value="category"),
            Choice(f"{c(TEXT, 'Individual')}         {SUBTEXT}pick specific services{RESET}",         value="individual"),
            Choice(f"{c(TEXT, 'Deploy everything')}  {SUBTEXT}bring the full stack up{RESET}",        value="all"),
            Choice(f"{c(TEXT, 'Core only')}          {SUBTEXT}proxy + DNS only{RESET}",               value="core"),
            Separator(),
            Choice(f"{c(SUBTEXT, 'Reconfigure .env')}  {SUBTEXT}re-run setup wizard{RESET}",          value="reconfigure"),
        ],
        style=MOCHA,
    ).ask()

    if mode is None:
        return

    if mode == "reconfigure":
        existing = load_env()
        values = run_setup(existing)
        if values:
            save_env(values)
            print(f"\n  {GREEN}✓ .env updated.{RESET}\n")
        return

    selected_ids, profiles = set(), []

    if mode == "all":
        selected_ids = {svc["id"] for svc in all_optional_services()}
        profiles = ["all"]
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
            print(f"\n  {GREEN}✓ Done.{RESET}\n")
        else:
            print(f"\n  {RED}✗ Something went wrong. Check the output above.{RESET}\n")
    else:
        cmd = build_command(profiles)
        print(f"\n  {SUBTEXT}Run manually:{RESET}  {TEXT}{cmd}{RESET}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {SUBTEXT}Cancelled.{RESET}\n")
