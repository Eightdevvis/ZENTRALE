"""Alle Texte des Befehls `zentrale` an einer Stelle.

Englisch (Bauplan v1: Zielgruppe international). Deutsch kommt später als
zweite Sprache dazu: ein zweites Wörterbuch DE mit denselben Schlüsseln und
`SPRACHE` nach Einstellung — der Code fasst keinen Text selbst an.
"""

EN = {
    # ── Banner und Hilfe ────────────────────────────────────────────
    "banner": (
        "╺━┓┏━╸┏┓╻╺┳╸┏━┓┏━┓╻  ┏━╸\n"
        "┏━┛┣╸ ┃┗┫ ┃ ┣┳┛┣━┫┃  ┣╸ \n"
        "┗━╸┗━╸╹ ╹ ╹ ╹┗╸╹ ╹┗━╸┗━╸"),
    "tagline": "your own hub: lists, calendar, notes, memory and an assistant — on every device",
    "usage": "Usage",
    "usage_line": "zentrale [command]",
    "usage_none": "Without a command, ZENTRALE opens in the terminal (TUI).",
    "group_start": "Start",
    "group_account": "Account",
    "group_sync": "Sync",
    "group_program": "Program",
    "examples": "Examples",
    "more_help": "Data stays on your devices; the cloud only ever sees encrypted bytes.",
    "cmd_tui": ("(no command)", "open ZENTRALE in this terminal"),
    "cmd_welcome": ("welcome", "a short tour: what ZENTRALE is and what to do first"),
    "cmd_setup": ("setup", "set up this device: log in, choose what to sync"),
    "cmd_login": ("login", "log in to your account on this device"),
    "cmd_logout": ("logout", "log out and remove the account key from this device"),
    "cmd_account_create": ("account create", "create an account (needs an invite code)"),
    "cmd_account_recover": ("account recover", "set a new password with your emergency key"),
    "cmd_account_password": ("account password", "change your password"),
    "cmd_sync": ("sync", "sync now with your account"),
    "cmd_status": ("status", "account, device, last sync, what is synced"),
    "cmd_devices": ("devices", "list all devices of your account"),
    "cmd_adapter": ("adapter", "connected services (AI keys, calendar) and which device bridges"),
    "cmd_adapter_setup": ("adapter setup", "bring in what this device already has connected"),
    "cmd_cloud_usage": ("cloud usage", "how close the cloud is to its free limits (operator only)"),
    "cmd_update": ("update", "download and install the newest version"),
    "cmd_version": ("version", "show the installed version"),
    "cmd_help": ("-h, --help", "this help"),
    "ex": [
        ("zentrale", "open the dashboard"),
        ("zentrale setup", "first steps on a new device"),
        ("zentrale sync && zentrale status", "sync, then see what happened"),
    ],
    "unknown_command": "Unknown command '{cmd}'. See 'zentrale --help'.",

    # ── Begrüßung ───────────────────────────────────────────────────
    "welcome_title": "Welcome to ZENTRALE",
    "welcome_body": (
        "ZENTRALE is one hub for your everyday life: lists, calendar, notes, graphs,\n"
        "a memory and an assistant that knows them. It runs on your own devices.\n"
        "\n"
        "With an account, all your devices share the same data. Everything is\n"
        "encrypted on the device before it leaves; the server never sees your\n"
        "password, your key or your content. Without an account ZENTRALE works\n"
        "purely locally."),
    "welcome_next": "Next steps",
    "welcome_steps": [
        ("zentrale setup", "log in (or stay local) and choose what to sync"),
        ("zentrale", "open the dashboard in this terminal"),
        ("zentrale --help", "all commands"),
    ],

    # ── Eingaben ────────────────────────────────────────────────────
    "ask_name": "username: ",
    "ask_password": "Password: ",
    "ask_password_new": "New password (at least {n} characters): ",
    "ask_password_again": "Repeat the password: ",
    "ask_password_old": "Current password: ",
    "ask_code": "Invite code: ",
    "ask_emergency": "Emergency key: ",
    "passwords_differ": "The passwords do not match. Please try again.",
    "yes_no": " [y/n] ",
    "yes_no_default_yes": " [Y/n] ",
    "cancelled": "Cancelled. Nothing was changed.",
    "working_key": "Deriving your key (this takes a moment) …",

    # ── Konto ───────────────────────────────────────────────────────
    "login_ok": "Logged in as {name} on device '{device}'.",
    "login_already": "Already logged in as {name}. Log out first to switch accounts.",
    "logout_ok": "Logged out. The account key was removed from this device.",
    "logout_none": "Nobody was logged in on this device.",
    "create_intro": ("Creating a ZENTRALE account. Your password never leaves this\n"
                     "device; only a derived login key does."),
    "emergency_title": "YOUR EMERGENCY KEY — shown only once",
    "emergency_warning": (
        "Write it down or store it in your password manager NOW.\n"
        "If you forget your password, this key is the ONLY way back to your data.\n"
        "Nobody — not even the ZENTRALE team — can recover your data without it."),
    "emergency_confirm": "Have you saved the emergency key somewhere safe?",
    "emergency_not_saved": "Account not created. Run 'zentrale account create' again when you are ready.",
    "create_ok": "Account created and logged in as {name}.",
    "recover_intro": "Set a new password with your emergency key. Your data stays as it is.",
    "recover_ok": "New password set. Logged in as {name}.",
    "password_ok": "Password changed. Your data and other devices are not affected; log in there with the new password.",
    "not_logged_in": "Not logged in. Run 'zentrale login' first (or 'zentrale setup').",

    # ── Einrichtung ─────────────────────────────────────────────────
    "setup_title": "Set up this device",
    "setup_first_run": "This is the first start on this device — let's set it up.",
    "setup_account_q": "How do you want to use ZENTRALE on this device?",
    "setup_account_opts": [
        ("login", "Log in to my account (sync with my other devices)"),
        ("create", "Create a new account (needs an invite code)"),
        ("local", "Stay local (no account, nothing leaves this device)"),
    ],
    "setup_choose_q": "What should this device sync?",
    "setup_choose_opts": [
        ("all", "Everything"),
        ("pick", "Let me choose"),
        ("none", "Clean slate (nothing for now; change later with 'zentrale setup')"),
    ],
    "setup_pick_title": "Choose which apps this device syncs",
    "setup_pick_help": "↑/↓ move · space toggle · a all · n none · enter confirm · q cancel",
    "setup_pick_fallback": "Numbers to toggle (e.g. '1 4'), 'a' all, 'n' none, Enter to confirm: ",
    "setup_local_ok": "Done. ZENTRALE runs locally on this device. Open it with 'zentrale'.",
    "setup_sync_now": "Syncing now …",
    "setup_done": "Done. Open ZENTRALE with 'zentrale'.",
    "setup_choice_saved": "This device syncs: {liste}.",
    "setup_choice_none": "This device syncs nothing for now (clean slate).",
    "number_choice": "Choose 1–{n}: ",

    # ── Apps und was sie haben (core/abgleich_apps.py) ───────────────
    "app": {
        "fokus": ("Lists", "to-dos, checklists, projects"),
        "notizen": ("Notes", "block notes"),
        "kalender": ("Calendar extras", "travel times, buffers, layers (events sync with your calendar provider)"),
        "graph": ("Graphs", "measurements like sleep, mood, habits"),
        "assistent": ("Assistant", "what it knows about you, chats, transcripts, feedback, costs"),
        "ablage": ("Documents", "files the assistant made or you attached"),
        "desk": ("Desk", "your canvases"),
        "werkstatt": ("Workshop", "apps you built and got from the shop"),
        "mail": ("Mail rules", "how mail is sorted (never passwords)"),
        "klavier": ("Melodies", "the piano"),
        "tutor": ("Tutor", "language tutor progress"),
        "cloud": ("Cloud", "account, sync, devices"),
        "adapter": ("Adapter", "connected services: AI keys, calendar bridge"),
    },
    "setup_apps_found": "Apps with data (on this device or in your account): {liste}",
    "setup_nothing_yet": "Nothing to sync yet — new apps will ask when they have data.",
    "ask_new_app": "{name} has data — sync it with your account?",
    "new_apps_hint": "Not synced yet, waiting for your decision: {liste}. Run 'zentrale sync' in a terminal.",

    # ── Abgleich ────────────────────────────────────────────────────
    "sync_first_fill": "Your account was empty — it is now filled from this device.",
    "sync_first_join": "First sync of this device: the account's data wins; differing local versions are kept aside.",
    "sync_result": "Fetched {geholt} · sent {gesendet} · moved aside {beiseite}",
    "sync_note": "  Note: {text}",
    "sync_busy": "Another sync is running right now. Try again in a moment.",
    "sync_conflicts_dir": "Kept versions: {ordner}",

    # ── Status ──────────────────────────────────────────────────────
    "st_account": "Account",
    "st_account_none": "not logged in (local only)",
    "st_server": "Cloud",
    "st_device": "Device",
    "st_version": "Version",
    "st_sync": "Last sync",
    "st_sync_never": "never",
    "st_sync_error": "Last error",
    "st_areas": "Syncs",
    "st_areas_all": "everything",
    "st_areas_none": "nothing",
    "st_apps": "Apps",
    "st_app_cloud_on": "on — syncs over your account",
    "st_app_cloud_off": "off — this device is local only",
    "st_app_on": "synced",
    "st_app_off": "stays on this device",
    "st_app_open": "not decided yet",
    "st_app_adapter": "always synced — {n} connection(s)",
    "st_way": "Sync way",
    "st_notes": "Notes",

    # ── Geräte ──────────────────────────────────────────────────────
    "dev_title": "Devices of {name}",
    "dev_none": "No devices yet.",
    "dev_registered": "This device is registered as '{name}'.",
    "dev_this": "(this device)",
    "hw": {"gpu": "GPU", "bildschirm": "display", "mikro": "mic", "lautsprecher": "speaker"},
    "dev_seen": "last seen {zeit}",

    # ── Adapter (core/adapter.py) ───────────────────────────────────
    "ad_title": "Adapter — connected services",
    "ad_none": "No connections yet. 'zentrale adapter setup' brings in what this device already has.",
    "ad_head": ("Connection", "Kind", "Feeds", "Bridge", "Status"),
    "ad_bridge_none": "— (every device uses it itself)",
    "ad_bridge_local": "this device (no account — local only)",
    "ad_bridge_free": "free — the next device that runs takes it",
    "ad_bridge_holds": "{wer} until {bis}",
    "ad_bridge_expired": "free (was {wer}, expired {bis})",
    "ad_keys": "{n} key(s) readable here",
    "ad_keys_unreadable": "{n} key(s) readable, {m} not readable on this device",
    "ad_cal_unknown": "no Google run seen yet",
    "ad_setup_ki": "AI keys moved into the Adapter (encrypted): {liste}",
    "ad_setup_ki_kept": "Kept in ai_config.json (the Adapter has a different value): {liste}",
    "ad_setup_ki_none": "No AI keys left to move.",
    "ad_setup_cal_created": ("Calendar connection 'google-kalender' created from this device's vdirsyncer setup.\n"
                             "Events now sync through your account; only one device at a time talks to Google."),
    "ad_setup_cal_exists": "Calendar connection already exists.",
    "ad_setup_cal_none": "No vdirsyncer setup on this device ({pfad}) — no calendar connection.",
    "ad_setup_cal_nopair": "The vdirsyncer setup has no pair writing into ZENTRALE's calendar folder — nothing created.",
    "ad_setup_next": "Next: 'zentrale sync' — then every device of your account has it.",

    # ── Cloud-Nutzung (core/cloud_nutzung.py) ───────────────────────
    "use_title": "Cloud usage — Cloudflare free tier",
    "use_asof": "as of {zeit} UTC",
    "use_period": {"day": "today (UTC)", "month": "this month (UTC)", "now": "right now"},
    "use_self": "self-counted",
    "use_both": "self-counted {selbst} · Cloudflare {cf} ({um})",
    "use_all_ok": "All limits are below 50 %.",
    "use_money": "Only R2 costs money above free; Workers and D1 simply stop until the next day.",
    "use_checked": "Limits checked {datum} against the Cloudflare docs.",
    "use_only_operator": "Sorry — usage figures are only for the operator of this cloud.",
    "use_warning": "Cloud free tier: {text}{weitere} See 'zentrale cloud usage'.",
    "use_more": " (+{n} more)",

    # ── Programm ────────────────────────────────────────────────────
    "version_line": "ZENTRALE {fassung} ({kanal})",
    "kanal": {"apt": "installed with apt", "pacman": "installed with pacman",
              "script": "installed with install.sh", "dev": "developer checkout"},
    "upd_check": "Checking for a new version …",
    "upd_current": "You have the newest version ({fassung}).",
    "upd_found": "New version {neu} (you have {alt}), {groesse}.",
    "upd_download": "Downloading …",
    "upd_bad_sha": "The download is damaged (checksum mismatch). Nothing was installed.",
    "upd_venv": "Installing Python packages (this may take a few minutes) …",
    "upd_ok": "Updated to {neu}. The old version stays in {alt_ordner} until the next update.",
    "upd_dev": ("This is a developer checkout ({wurzel}), not an installed hub.\n"
                "Update it with git instead."),
    "upd_paket_apt": ("ZENTRALE was installed with apt, so apt updates it:\n"
                      "  sudo apt update && sudo apt upgrade"),
    "upd_paket_pacman": ("ZENTRALE was installed with pacman, so update it the same way\n"
                         "(pacman -Syu, or your AUR helper)."),
    "upd_need_login": "Log in first ('zentrale login') — downloads need your account or an invite code.",
    "tui_missing": "The terminal view could not be started: {grund}",

    # ── Fehler ──────────────────────────────────────────────────────
    "error": "Error: {text}",
    "interrupted": "\nInterrupted.",
}

SPRACHE = EN


def t(schluessel, **werte):
    text = SPRACHE[schluessel]
    return text.format(**werte) if werte and isinstance(text, str) else text
