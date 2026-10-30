"""Alle Texte des Befehls `zentrale` an einer Stelle.

Englisch (Bauplan v1: Zielgruppe international). Deutsch kommt später als
zweite Sprache dazu: ein zweites Wörterbuch DE mit denselben Schlüsseln und
`SPRACHE` nach Einstellung — der Code fasst keinen Text selbst an.

Since 2026-10-29: translations come from gettext (core/i18n.py, see
"Translations" below), not from a second dict. German is the first UI language.
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
    "cmd_setup": ("setup", "the setup wizard: account, cloud folder, updates, background, apps"),
    "cmd_login": ("login", "log in to your account on this device"),
    "cmd_logout": ("logout", "log out and remove the account key from this device"),
    "cmd_account_create": ("account create", "create an account (needs an invite code)"),
    "cmd_account_recover": ("account recover", "set a new password with your emergency key"),
    "cmd_account_password": ("account password", "change your password"),
    "cmd_sync": ("sync", "sync now with your account (--automatic: quiet, for the timer)"),
    "cmd_status": ("status", "account, device, last sync, what is synced"),
    "cmd_devices": ("devices", "list all devices of your account"),
    "cmd_devices_remove": ("devices remove <name>", "remove another device (sold, lost, stolen) from your account"),
    "cmd_leave": ("leave", "take this device out of your account (data stays unless you ask)"),
    "cmd_adapter": ("adapter", "connected services (AI keys, calendar) and which device bridges"),
    "cmd_adapter_setup": ("adapter setup", "bring in what this device already has connected"),
    "cmd_adapter_run": ("adapter run", "run the calendar bridge once (what the timer does)"),
    "cmd_adapter_calendar": ("adapter calendar [google|zencloud|lokal]", "show or switch where the calendar comes from"),
    "cmd_timers": ("timers", "the background timers: sync and calendar bridge"),
    "cmd_timers_install": ("timers install", "install or repair the timers and start them"),
    "cmd_timers_remove": ("timers remove", "stop the timers and remove them"),
    "cmd_cloud_usage": ("cloud usage", "how close the cloud is to its free limits (operator only)"),
    "cmd_update": ("update", "download and install the newest version (auto on|off: by itself, daily)"),
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
    "yes_no_default_no": " [y/N] ",
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
        "cloud_folder": ("Cloud folder", "anything you drop into ~/Zentrale/Cloud"),
        "adapter": ("Adapter", "connected services: AI keys, calendar bridge"),
    },
    "setup_apps_found": "Apps with data (on this device or in your account): {liste}",
    "setup_nothing_yet": "Nothing to sync yet — new apps will ask when they have data.",

    # ── Setup wizard (zentrale_cli/wizard.py, building kit 5.1) ──────
    "choice_default": "(default)",
    "choice_prompt": "Choose 1–{n}",
    "choice_prompt_default": ", Enter = {n}",
    "choice_prompt_back": ", b = back",
    "wiz_step": "Step {n} of {total}",
    "wiz_resume": "Picking up where you left off.",
    "wiz_logged_in": "Logged in as {name}.",
    "wiz_cloud_folder_q": "A folder that syncs: anything you drop into {pfad} is on all your devices. Use it?",
    "wiz_cloud_folder_opts": [
        ("yes", "Yes, sync the cloud folder"),
        ("no", "No, not on this device"),
    ],
    "wiz_auto_update_q": "Install new versions of ZENTRALE automatically (once a day)?",
    "wiz_auto_update_opts": [
        ("on", "Yes, keep this device up to date by itself"),
        ("off", "No, only tell me that an update is available"),
    ],
    "wiz_linger_q": "Keep syncing when nobody is logged in on this device (e.g. after a reboot)?",
    "wiz_linger_opts": [
        ("yes", "Yes, run in the background from boot"),
        ("no", "No, only while I am logged in"),
    ],
    "wiz_linger_on": "This device now syncs also when nobody is logged in.",
    "wiz_linger_refused": ("Your system did not allow it for your user ({text}).\n"
                           "An administrator can allow it once with: loginctl enable-linger {user}\n"
                           "Until then this device syncs only while you are logged in."),
    "wiz_linger_off": "This device syncs only while you are logged in ('zentrale setup' to change it).",
    "wiz_purpose_q": "What is this device for — which apps live here?",

    # ── Updates (zentrale_cli/aktualisieren.py, building kit 5.3) ────
    "st_auto_update": "Auto-update",
    "st_auto_on": "on (daily)",
    "st_auto_off": "off",
    "st_auto_package": "by your package manager",
    "st_background": "Background",
    "st_linger_on": "keeps syncing when you are logged out",
    "st_linger_off": "syncs only while you are logged in",
    "upd_hint": "Update available: {alt} → {neu} ('zentrale update').",
    "upd_hint_package": "Update available: {alt} → {neu} — your package manager installs it.",
    "upd_hint_failed": "Update to {neu} failed its self-test; staying on {alt}. 'zentrale update' tries again.",
    "upd_self_test": "Self-test of {neu} …",
    "upd_self_test_failed": "Version {neu} failed its self-test. Staying on {alt}; nothing was switched.",
    "upd_backend_restarted": "The running backend was restarted with the new version.",
    "upd_auto_unreachable": "Could not check for updates: {text}",
    "upd_auto_on": "Auto-update is on: new versions install by themselves once a day.",
    "upd_auto_off": "Auto-update is off: 'zentrale status' says when an update is available.",
    "upd_usage": "Use 'zentrale update', 'zentrale update --automatic' or 'zentrale update auto [on|off]'.",
    "check_imports": "Self-test: program loads.",
    "check_settings": "Self-test: settings readable.",
    "check_cloud": "Self-test: cloud reachable.",
    "check_cloud_skipped": "Self-test: no account and no public source — cloud not checked.",
    "check_failed": "Self-test failed: {text}",
    "tm_healed": "New version since the timers were last set up — refreshed: {liste}",
    "ask_new_app": "{name} has data — sync it with your account?",
    "new_apps_hint": "Not synced yet, waiting for your decision: {liste}. Run 'zentrale sync' in a terminal.",

    # ── Abgleich ────────────────────────────────────────────────────
    "sync_first_fill": "Your account was empty — it is now filled from this device.",
    "sync_first_join": "First sync of this device: the account's data wins; differing local versions are kept aside.",
    "sync_result": "Fetched {geholt} · sent {gesendet} · moved aside {beiseite}",
    "sync_note": "  Note: {text}",
    "sync_busy": "Another sync is running right now. Try again in a moment.",
    "sync_keys_new": "AI keys arrived or changed: {liste}.",
    "sync_keys_restarted": "The backend reads keys only when it starts — restarted {unit}.",
    "sync_keys_restart": "The backend reads keys only when it starts: if ZENTRALE is open, quit and start it again.",
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
    "st_held_back": "Not synced (held back, everything else syncs)",
    "st_held_too_large": "  {path} — too large for the cloud ({size} MiB)",
    "st_held_folder": "  {n} files of the cloud folder — the folder is missing or empty on this device",

    # ── Geräte ──────────────────────────────────────────────────────
    "devices_title": "Devices of {name}",
    "devices_none": "No devices yet.",
    "dev_registered": "This device is registered as '{name}'.",
    "dev_this": "(this device)",
    "hw": {"gpu": "GPU", "bildschirm": "display", "mikro": "mic", "lautsprecher": "speaker"},
    "dev_seen": "last seen {zeit}",
    # Build steps 7 and 8 (memory/hub/building_kit_plan.md)
    "dev_insecure": "insecure version since {since} — {link}",
    "dev_removed": "removed {zeit} (from {by})",
    "dev_left": "left {zeit}",
    "st_insecure": "Security",
    "st_insecure_text": ("this version ({version}) is marked insecure since {since} — {link}\n"
                         "It keeps syncing. Update with 'zentrale update', or remove this device."),
    "st_removed": "Removed",
    "st_removed_text": ("this device was removed from your account ({zeit}). 'zentrale login' adds it\n"
                        "back; 'zentrale leave' finishes leaving."),
    "sync_removed": ("This device was removed from your account. Run 'zentrale login' to add it back, "
                     "or 'zentrale leave' to finish leaving."),
    "leave_intro": ("'{device}' leaves the account {name}: it disappears from your devices, is logged\n"
                    "out here and its background timers stop. Your data in the cloud and on your\n"
                    "other devices stays."),
    "leave_local": "This device is not logged in. Leaving only stops its background timers.",
    "leave_confirm": "Leave now?",
    "leave_offline": ("The cloud was not reachable: logged out here, but '{device}' still shows in\n"
                      "'zentrale devices'. Remove it from another device: 'zentrale devices remove {device}'."),
    "leave_delete_ask": "Also delete the ZENTRALE data on this device ({paths})?",
    "leave_delete_checkout": "This is a developer checkout: 'leave' never deletes its data.",
    "leave_done": "'{device}' has left. The data on this device was kept.",
    "leave_done_deleted": "'{device}' has left. The data on this device was deleted.",
    "rm_usage": "Usage: zentrale devices remove <name>",
    "rm_self": "'{device}' is this device. Use 'zentrale leave' to take it out.",
    "rm_intro": ("Remove '{device}' from your account? It is logged out at once and its next sync\n"
                 "says it was removed. What is stored on that device itself stays there."),
    "rm_confirm": "Remove '{device}'?",
    "rm_done": "'{device}' was removed ({n} session(s) ended).",
    "rm_lost": "Was the device lost or stolen?",
    "rot_offer": ("Whoever has it may have your account key and what was synced to it. Changing\n"
                  "the account key protects everything from now on:\n"
                  "  • every file in the cloud is encrypted again with a new key,\n"
                  "  • you get a NEW emergency key — the old one stops working,\n"
                  "  • ALL your other devices, the phone too, are logged out and must log in again."),
    "rot_ask": "Change the account key now?",
    "rot_not_now": "The account key stays as it is.",
    "rot_new_password": "New password too (Enter = keep the current one): ",
    "rot_sync_first": "Syncing first, so nothing of this device is left out …",
    "rot_working": "Encrypting everything again with the new key …",
    "rot_emergency_not_saved": "The account key was not changed.",
    "rot_done": "The account key was changed ({n} files). Log in again on your other devices.",
    "rot_inbox_skipped": "{n} unreadable file(s) in a phone inbox were dropped.",

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
    "ad_run_not_google": "Calendar source is '{quelle}', not google — no Google sync.",
    "ad_cal_source": "Calendar source: {quelle}",
    "ad_cal_source_default": " (not set — the default)",
    "ad_cal_source_how": ("Switch with 'zentrale adapter calendar google|zencloud|lokal' — the same setting on\n"
                          "every device; nothing is ever deleted."),
    "ad_cal_source_bad": "Unknown calendar source '{wort}' — use one of: {liste}",
    "ad_cal_source_same": "Calendar source is already {quelle}.",
    "ad_cal_set": "Calendar source: {von} → {quelle}. Every device follows after its next sync.",
    "ad_cal_hub_fuellt": "Your account had no calendar yet: this device's calendar fills it.",
    "ad_cal_hub_uebernimmt": ("Your account already has a calendar: it wins. This device's old calendar\n"
                              "is set aside (never deleted) — pick from it yourself."),
    "ad_cal_aside": "Set aside: {pfad}",
    "ad_cal_hub_no_account": "Not logged in — the calendar can only sync through your account. Run 'zentrale login' first.",
    "ad_cal_hub_unknown": ("Could not find out whether your account already has a calendar (offline?) —\n"
                           "nothing changed. Try again when online."),
    "ad_cal_hub_offline": "Could not sync ({text}) — nothing switched. Try again when online.",
    "ad_cal_hub_sync_later": "Switched, but the sync afterwards failed ({text}) — the next 'zentrale sync' catches up.",
    "ad_cal_uploading": "Uploading the calendar to the cloud ({n} files) — this can take a few minutes …",
    "ad_cal_syncing": "Syncing the calendar with the cloud ({n} files on this device) — this can take a few minutes …",
    "ad_cal_still": "  … still syncing ({s} s)",
    "ad_cal_done": "  done after {s} s.",
    "ad_cal_open": ("This device's calendar is not fully in the cloud yet. The next sync finishes it —\n"
                    "or run 'zentrale adapter calendar zencloud' again now."),
    "ad_cal_interrupted": ("Interrupted — the calendar source stays zencloud, nothing was deleted.\n"
                           "The upload is not finished: run 'zentrale adapter calendar zencloud' again,\n"
                           "or let the next automatic sync finish it."),
    "ad_cal_continued": "Calendar source is zencloud — the unfinished first sync of the calendar is now done.",
    "ad_cal_continue_failed": ("Calendar source is zencloud, but the first sync of the calendar is still not done\n"
                               "({text}) — the next sync tries again. Nothing was deleted."),
    "ad_run_nothing": "No calendar connection and no vdirsyncer setup on this device — nothing to do.",

    # ── Timer (zentrale_cli/timer.py) ───────────────────────────────
    "tm_title": "Timers — run in the background while you are logged in",
    "tm_none": ("systemd for your user is not available here, so there are no background timers.\n"
                "Sync by hand with 'zentrale sync'; the calendar bridge stays with your other devices."),
    "tm_on": "Timers on: sync every 5 min, calendar bridge every 3 min, updates daily.",
    "tm_written": "Timer files written: {liste}",
    "tm_replaced": "Replaced old timer files (developer links or hand-made): {liste}",
    "tm_up_to_date": "Timer files already up to date.",
    "tm_error": "systemd did not start the timers: {text}",
    "tm_removed": "Timers stopped and removed: {liste}",
    "tm_left": "Stopped but left in place (not written by zentrale): {liste}",
    "tm_nothing_removed": "Timers stopped; no timer files of zentrale here.",
    "tm_command": "Command in the timers: {pfad}",
    "tm_head": ("Timer", "Files", "Enabled", "Active", "Next run", "Last result"),
    "tm_file": {"fehlt": "missing", "eigen": "ok", "alt": "outdated",
                "verweis": "old link", "fremd": "not from zentrale"},
    "tm_fix": "Install or repair: 'zentrale timers install'.",
    "tm_usage": "Use 'zentrale timers', 'zentrale timers install' or 'zentrale timers remove'.",
    "vd_ok": "Calendar bridge: vdirsyncer found — this device can take the bridge to Google.",
    "vd_missing": ("Calendar bridge: vdirsyncer is not installed. This device gets the calendar\n"
                   "through the cloud but never talks to Google itself. To let it take the bridge,\n"
                   "{wie}."),
    "vd_how": {"pacman": "install the package 'vdirsyncer' with pacman",
               "apt": "install the package 'vdirsyncer' with apt",
               "sonst": "install vdirsyncer with your package manager (or pipx)"},

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
    "upd_keeper_failed": ("The background timers could not be refreshed for the new version.\n"
                          "Run 'zentrale timers install' to repair them."),
    "upd_dev": ("This is a developer checkout ({wurzel}), not an installed hub.\n"
                "Update it with git instead."),
    "upd_paket_apt": ("ZENTRALE was installed with apt, so apt updates it:\n"
                      "  sudo apt update && sudo apt upgrade"),
    "upd_paket_pacman": ("ZENTRALE was installed with pacman, so update it the same way\n"
                         "(pacman -Syu, or your AUR helper)."),
    "upd_need_login": "Log in first ('zentrale login') — downloads need your account or an invite code.",
    "tui_missing": "The terminal view could not be started: {grund}",

    # ── Developer installer mode (zentrale_cli/dev.py, devkit/) ─────
    "dev_only_checkout": ("'zentrale dev' only works in a developer checkout with its venv\n"
                          "(it needs devkit/, which is never in the package)."),
    "dev_title": "Developer installer mode — profiles (isolated ZENTRALE homes)",
    "dev_root": "Dev root: {root}",
    "dev_none": "No profiles yet.",
    "dev_line": "  {name:<12} {state:<10} start {release:<8} now {installed:<8} account {account:<12} {online}",
    "dev_online": "online",
    "dev_offline": "offline",
    "dev_broken": "  (broken — reset it)",
    "dev_usage": [
        "zentrale dev new <name> [--state S] [--release N] [--account A] [--step n]   make a profile",
        "zentrale dev states                 the start states",
        "zentrale dev shell <name>           a shell inside the profile (type 'zentrale …' there)",
        "zentrale dev run <name> <words …>   run the profile's 'zentrale' with these words",
        "zentrale dev update <name> <M>      play an update to release M (keeper included)",
        "zentrale dev reset <name>           back to its start state",
        "zentrale dev delete <name>          remove the profile (its account stays in the fake cloud)",
        "zentrale dev release [N]            list local releases, or build release N from this checkout",
        "zentrale dev cloud-reset            empty the fake cloud (all accounts)",
    ],
    "dev_bad_use": "Wrong use of 'zentrale dev'. Run 'zentrale dev' alone to see how it works.",
    "dev_state_line": "{state:<10} {steps}",
    "dev_state_later": "   (not built yet — comes with {planned})",
    "dev_states_release": "Every state takes --release N: the profile starts on that release.",
    "dev_step": "  {name}: {step} …",
    "dev_made": "Profile {name} is ready: state {state}, release {release}.",
    "dev_reset_ok": "Profile {name} is back at {state}.",
    "dev_deleted": "Profile {name} removed.",
    "dev_shell": "Shell inside profile {name} (its own HOME, fake systemd, fake cloud). Leave it with 'exit'.",
    "dev_update": "Update in {name}: {before} → {after}",
    "dev_release_built": "Built {path}",
    "dev_releases": "Local releases: {liste}",
    "dev_releases_none": "No local releases yet — 'zentrale dev new' builds the one it needs.",
    "dev_cloud_reset": "The fake cloud is empty now.",
    "dev_bad_name": "'{name}' is not a profile name: 3–32 characters a–z, 0–9, '.', '_', '-', starting with a letter.",
    "dev_no_profile": "There is no profile '{name}'. See 'zentrale dev list'.",
    "dev_exists": "Profile '{name}' exists already — 'zentrale dev reset {name}' or pick another name.",
    "dev_not_installed": "Profile '{name}' has no installed 'zentrale' — reset it.",
    "dev_no_venv": "Run 'zentrale dev' from the checkout's venv: profiles link it instead of building their own.",
    "dev_unknown_state": "Unknown state '{state}'. States: {states}.",
    "dev_state_planned": "State '{state}' needs the step(s) {steps}, which are not built yet ({planned}).",
    "dev_install_failed": "install.sh failed in the profile:\n{output}",
    "dev_login_failed": "'zentrale setup' failed in the profile:\n{output}",
    "dev_guard_root": "Refused: {path} is or touches the real installation (or the checkout). Pick another ZENTRALE_DEV_ROOT.",
    "dev_guard_path": "Refused: {path} is outside the dev root.",
    "dev_guard_env": "Refused: {variable}={path} would reach outside the profile.",

    # ── Fehler ──────────────────────────────────────────────────────
    "error": "Error: {text}",
    "interrupted": "\nInterrupted.",
}

SPRACHE = EN


# ── Translations (Sasha 2026-10-29: UI text through gettext) ───────────
#
# The English text in EN is the msgid; the core's one table translates it
# (core/i18n.py, core/locale/<lang>/LC_MESSAGES/zentrale.po + .mo). German
# is the first UI language, ZENTRALE_LANG picks another; a text without a
# translation stays English.


def t(schluessel, **werte):
    text = SPRACHE[schluessel]
    if isinstance(text, str):
        import i18n             # core/ (on the path via zentrale_cli/__init__)
        text = i18n._(text)
    return text.format(**werte) if werte and isinstance(text, str) else text
