# core/mail.py
#
# Das Mail-Triage-System der ZENTRALE: IMAP rein, sortieren, zurückschreiben.
#
# ── Was es tut ────────────────────────────────────────────────────────
# Pollt periodisch die INBOX jedes konfigurierten Kontos (Proton via Bridge,
# Gmail, Outlook), klassifiziert jede NEUE Mail über die Sender-Keymap
# (core/mail_rules.py) und führt die Kategorie-Aktion AM SERVER aus:
# verschiebt in den passenden Ordner bzw. in den Papierkorb. Damit lebt die
# Sortierung nicht nur in ZENTRALE, sondern echt im Quell-Postfach.
#
# ── Provider ──────────────────────────────────────────────────────────
# Alles spricht Standard-IMAP — die Unterschiede sind nur Config:
#   proton  -> Proton BRIDGE auf 127.0.0.1:1143 (STARTTLS, self-signed Cert).
#              Setzt einen laufenden Bridge-Daemon + bezahlten Plan voraus.
#   gmail   -> imap.gmail.com:993 (SSL), App-Passwort (2FA vorausgesetzt).
#   outlook -> outlook.office365.com:993 (SSL), OAuth2/XOAUTH2 (Azure-App).
# Zugangsdaten kommen verschlüsselt aus core/mail_secrets.py.
#
# ── Safe-by-default ───────────────────────────────────────────────────
# - DRY-RUN ist standardmäßig AN (Env MAIL_DRY_RUN, Default "1"): der Poller
#   klassifiziert + loggt, was er TÄTE, fasst aber nichts am Server an.
# - Aktionen sind umkehrbar (MOVE in Ordner / Papierkorb), KEIN Expunge der
#   Quelle über das Move hinaus, kein Hard-Delete.
# - Unbekannte Absender -> Review-Ordner, NIE eine destruktive Aktion.
#
# ── Transparenz ───────────────────────────────────────────────────────
# IMAP läuft NICHT durch core/net.py (das ist HTTP). Damit ausgehender Mail-
# Traffic trotzdem im orangenen Internet-Panel sichtbar ist, loggt jeder
# Poll-Lauf explizit über state.push_internet_log (wie der SearXNG-localhost-
# Fall im News-System).

import os
import sys
import ssl
import json
import time
import imaplib
import threading
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

# core/ auf den Pfad, damit `import state` auch bei `python -m core.mail`
# greift (Modul-Start legt nur das Projekt-Root auf sys.path, nicht core/).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state          # Log-Streams (stdout + Dashboard-Panel + Internet-Panel)
import mail_rules      # die Sender->Kategorie-Keymap (reine Triage-Logik)
import mail_secrets    # verschlüsselter Zugangsdaten-Speicher

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE = os.path.join(_DIR, "data", "mail_state.json")
_state_lock = threading.Lock()

# Wie viele klassifizierte Mails wir fürs Dashboard vorhalten.
_ITEMS_CAP = 200

# Provider-Vorlagen. `security`: ssl | starttls. `auth`: password | oauth2.
PROVIDERS = {
    "proton":  {"host": "127.0.0.1",                "port": 1143, "security": "starttls",
                "verify": False, "auth": "password"},
    "gmail":   {"host": "imap.gmail.com",           "port": 993,  "security": "ssl",
                "verify": True,  "auth": "password"},
    "outlook": {"host": "outlook.office365.com",    "port": 993,  "security": "ssl",
                "verify": True,  "auth": "oauth2"},
}

# Ordner-Prefix für die Kategorie-Ordner, die wir bei Bedarf anlegen.
FOLDER_PREFIX = os.environ.get("MAIL_FOLDER_PREFIX", "ZENTRALE")


def _dry_run():
    return os.environ.get("MAIL_DRY_RUN", "1") not in ("0", "false", "no", "off")


def _enabled():
    return os.environ.get("ZENTRALE_MAIL", "").lower() in ("1", "on", "true", "yes")


# ── Store (Watermark pro Konto + letzte klassifizierte Mails) ─────────

def _load_state():
    if not os.path.exists(_STATE):
        return {"accounts": {}, "items": []}
    try:
        with open(_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"accounts": {}, "items": []}


def _save_state(data):
    os.makedirs(os.path.dirname(_STATE), exist_ok=True)
    tmp = _STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATE)


def _watermark(name):
    return int(_load_state()["accounts"].get(name, {}).get("uid_watermark", 0))


def _set_watermark(name, uid):
    with _state_lock:
        data = _load_state()
        data["accounts"].setdefault(name, {})["uid_watermark"] = int(uid)
        data["accounts"][name]["last_poll"] = datetime.now().isoformat(timespec="seconds")
        _save_state(data)


def _record(item):
    with _state_lock:
        data = _load_state()
        data["items"].insert(0, item)
        data["items"] = data["items"][:_ITEMS_CAP]
        _save_state(data)


def recent(limit=50):
    """Die zuletzt klassifizierten Mails (fürs Dashboard / KI-Tool)."""
    return _load_state()["items"][:limit]


def counts():
    """Kategorie -> Anzahl über die zuletzt klassifizierten Mails. Fürs
    Dashboard-Panel (Zähler) und als Kurzfassung im KI-Tool."""
    out = {}
    for it in recent(200):
        out[it["category"]] = out.get(it["category"], 0) + 1
    return out


def review_stack(limit=20):
    """Die noch nicht zugeordneten Mails (unbekannte Absender → Review).
    Das ist Sashas Arbeitsstapel: hier wartet, was eine Zuordnung braucht."""
    return [it for it in recent(200)
            if not it.get("known")][:limit]


# ── KI-Tool: lies_mail (read-only, lokal, kein Permission-Gate) ────────
def lies(modus: str = "") -> str:
    """KI-Tool 'lies_mail'. Liest NUR den lokalen Triage-Stand (data/
    mail_state.json) — kein IMAP, kein Netz, nichts wird verschoben.

    - modus leer/"" (Default): Überblick — Zähler je Kategorie + der
      Review-Stapel (unbekannte Absender, die eine Zuordnung brauchen).
    - modus "review": nur der Review-Stapel, ausführlicher.
    """
    items = recent(200)
    if not items:
        return ("Noch keine Mails klassifiziert. Entweder lief noch kein "
                "Poll, oder ZENTRALE_MAIL ist aus.")

    stack = review_stack(20)

    def _line(it, i=None):
        who = mail_rules.normalize(it.get("from", "")) or "?"
        subj = (it.get("subject") or "").strip()[:60] or "(kein Betreff)"
        pre = f"{i}. " if i else "- "
        return f"{pre}{who} — «{subj}» [{it.get('account','?')}]"

    if (modus or "").strip().lower() == "review":
        if not stack:
            return "Der Review-Stapel ist leer — kein unbekannter Absender offen."
        lines = [_line(it, i) for i, it in enumerate(stack, 1)]
        return ("Review-Stapel (unbekannte Absender, warten auf Zuordnung):\n"
                + "\n".join(lines))

    cnt = counts()
    cat_lines = [f"- {cat}: {n}" for cat, n in
                 sorted(cnt.items(), key=lambda kv: -kv[1])]
    parts = [f"Mail-Triage — {len(items)} Mails klassifiziert.",
             "", "Je Kategorie:", *cat_lines]
    if stack:
        parts += ["", f"Review-Stapel ({len(stack)} offen):",
                  *[_line(it) for it in stack[:10]]]
        if len(stack) > 10:
            parts.append(f"  … und {len(stack) - 10} weitere.")
    else:
        parts += ["", "Review-Stapel: leer."]
    return "\n".join(parts)


# ── IMAP-Verbindung ───────────────────────────────────────────────────

def _provider_cfg(account):
    base = dict(PROVIDERS.get(account.get("provider", ""), {}))
    # Konto darf host/port/security überschreiben (z.B. anderer Bridge-Port).
    for k in ("host", "port", "security", "verify", "auth"):
        if account.get(k) is not None:
            base[k] = account[k]
    return base


def _connect(account):
    cfg = _provider_cfg(account)
    host, port = cfg["host"], int(cfg["port"])
    if cfg.get("security") == "ssl":
        ctx = ssl.create_default_context()
        if not cfg.get("verify", True):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    else:
        imap = imaplib.IMAP4(host, port)
        if cfg.get("security") == "starttls":
            ctx = ssl.create_default_context()
            if not cfg.get("verify", True):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            imap.starttls(ssl_context=ctx)

    if cfg.get("auth") == "oauth2":
        # XOAUTH2: frisches Access-Token holen (Refresh über den gespeicherten
        # refresh_token, core/mail_oauth.py). Token NIE persistiert, nur im RAM.
        import mail_oauth
        user = account["user"]
        token = mail_oauth.access_token_for(account)
        auth_str = f"user={user}\x01auth=Bearer {token}\x01\x01"
        imap.authenticate("XOAUTH2", lambda _=None: auth_str.encode("utf-8"))
    else:
        imap.login(account["user"], account["secret"])
    return imap


# ── Header-Parsing ────────────────────────────────────────────────────

def _decode(raw):
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _parse_headers(raw_bytes):
    import email
    msg = email.message_from_bytes(raw_bytes)
    when = ""
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        when = dt.isoformat(timespec="seconds") if dt else ""
    except Exception:
        when = ""
    return {
        "from": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")),
        "date": when,
        "message_id": (msg.get("Message-ID") or "").strip(),
    }


# ── Ordner-Auflösung + Write-back ─────────────────────────────────────

def _list_folders(imap):
    typ, data = imap.list()
    folders = []
    if typ == "OK":
        for line in data or []:
            if isinstance(line, bytes):
                line = line.decode("utf-8", "replace")
            folders.append(line)
    return folders


def _find_trash(imap):
    """Papierkorb über das SPECIAL-USE-Attribut \\Trash finden, sonst raten."""
    for line in _list_folders(imap):
        low = line.lower()
        if "\\trash" in low:
            # Ordnername steht am Zeilenende in Anführungszeichen.
            name = line.split('"')[-2] if '"' in line else line.split()[-1]
            return name
    for guess in ("Trash", "[Gmail]/Trash", "Deleted", "Deleted Items", "Papierkorb"):
        return guess  # erster Treffer als pragmatischer Fallback
    return "Trash"


def _ensure_folder(imap, name):
    """Legt einen Ordner an, falls er fehlt (idempotent)."""
    existing = []
    for line in _list_folders(imap):
        if '"' in line:
            existing.append(line.split('"')[-2])
    if name not in existing:
        try:
            imap.create(name)
        except Exception:
            pass
    return name


def _target_folder(imap, action_spec):
    if action_spec.get("action") == "trash":
        return _find_trash(imap)
    folder = action_spec.get("folder") or f"{FOLDER_PREFIX}/Review"
    return _ensure_folder(imap, folder)


def _move_uid(imap, uid, target):
    """UID nach `target` verschieben. UID MOVE (RFC 6851) bevorzugt, sonst
    COPY + \\Deleted + EXPUNGE als Fallback. Beides ist umkehrbar (die Mail
    liegt danach im Zielordner)."""
    uid = str(uid)
    has_move = b"MOVE" in (imap.capabilities or ())
    if has_move:
        typ, _ = imap.uid("MOVE", uid, _q(target))
        if typ == "OK":
            return True
    typ, _ = imap.uid("COPY", uid, _q(target))
    if typ != "OK":
        return False
    imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
    imap.expunge()
    return True


def _q(name):
    # IMAP-Mailbox-Name quoten (Ordner mit Leer-/Sonderzeichen).
    return '"' + name.replace('"', '\\"') + '"'


# ── Ein Konto pollen ──────────────────────────────────────────────────

def poll_account(account, dry_run=None):
    """Holt neue Mails eines Kontos, klassifiziert + (optional) sortiert.

    Liefert eine Liste der klassifizierten Items (auch im Dry-Run).
    """
    if dry_run is None:
        dry_run = _dry_run()
    name = account["name"]
    cfg = _provider_cfg(account)
    mode = "DRY-RUN" if dry_run else "LIVE"
    state.push_log(f"MAIL [{name}]: poll {cfg['host']}:{cfg['port']} ({mode})")
    state.push_internet_log(f"IMAP {name} → {cfg['host']}:{cfg['port']} ({mode})")

    imap = _connect(account)
    results = []
    try:
        imap.select("INBOX")
        last = _watermark(name)
        # Alle UIDs echt größer als der Watermark holen.
        typ, data = imap.uid("SEARCH", None, f"UID {last + 1}:*")
        uids = []
        if typ == "OK" and data and data[0]:
            for u in data[0].split():
                u = int(u)
                if u > last:            # IMAP gibt bei x:* min. eine UID zurück
                    uids.append(u)
        if not uids:
            state.push_log(f"MAIL [{name}]: nichts Neues (UID > {last})")
            return results

        highest = last
        for uid in sorted(uids):
            typ, fetched = imap.uid("FETCH", str(uid),
                                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                highest = max(highest, uid)
                continue
            hdr = _parse_headers(fetched[0][1])
            category, known = mail_rules.classify(hdr["from"])
            spec = mail_rules.category_action(category)

            item = {
                "account": name,
                "uid": uid,
                "from": hdr["from"],
                "subject": hdr["subject"],
                "date": hdr["date"],
                "category": category,
                "known": known,
                "action": spec.get("action", "move"),
                "applied": False,
                "dry_run": dry_run,
                "seen_at": datetime.now().isoformat(timespec="seconds"),
            }

            if not dry_run:
                try:
                    target = _target_folder(imap, spec)
                    if _move_uid(imap, uid, target):
                        item["applied"] = True
                        item["target"] = target
                except Exception as e:
                    state.push_log(f"MAIL [{name}]: Aktion fehlgeschlagen "
                                   f"(uid {uid}): {type(e).__name__}: {e}")

            flag = "✓" if item["applied"] else ("·" if dry_run else "✗")
            tag = category if known else f"{category} (neu)"
            state.push_log(f"MAIL [{name}] {flag} «{hdr['subject'][:48]}» "
                           f"<{mail_rules.normalize(hdr['from'])}> → {tag}")
            _record(item)
            results.append(item)
            highest = max(highest, uid)

        # Watermark NUR im Live-Modus vorrücken — sonst würde ein Dry-Run die
        # Mails "verbrauchen", ohne sie je wirklich sortiert zu haben.
        if not dry_run:
            _set_watermark(name, highest)
        return results
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def poll_all(dry_run=None):
    accounts = [a for a in mail_secrets.load_accounts() if a.get("enabled", True)]
    if not accounts:
        state.push_log("MAIL: keine Konten konfiguriert (siehe "
                       "core.mail_secrets add) — übersprungen")
        return []
    out = []
    for acct in accounts:
        try:
            out.extend(poll_account(acct, dry_run=dry_run))
        except Exception as e:
            state.push_log(f"MAIL [{acct.get('name','?')}]: Poll fehlgeschlagen — "
                           f"{type(e).__name__}: {e}")
    return out


# ── periodischer Fetcher (aus main.py) ────────────────────────────────

def start_fetcher():
    """Daemon-Thread: pollt alle MAIL_INTERVAL_MIN Minuten. Gegated über
    ZENTRALE_MAIL=on; default AUS, damit nichts ungewollt nach Hause telefoniert.
    """
    if not _enabled():
        return False
    if not mail_secrets.available():
        state.push_log("MAIL: ZENTRALE_MAIL=on, aber keine Passphrase/cryptography "
                       "— Fetcher startet nicht")
        return False

    interval_min = float(os.environ.get("MAIL_INTERVAL_MIN", "10"))
    delay_s = float(os.environ.get("MAIL_START_DELAY_S", "30"))

    def _loop():
        time.sleep(delay_s)
        state.push_log(f"MAIL: Fetcher aktiv (alle {interval_min:.0f} min, "
                       f"{'DRY-RUN' if _dry_run() else 'LIVE'})")
        while True:
            try:
                poll_all()
            except Exception as e:
                state.push_log(f"MAIL: Fetcher-Lauf abgebrochen — {type(e).__name__}: {e}")
            time.sleep(interval_min * 60)

    threading.Thread(target=_loop, name="mail-fetcher", daemon=True).start()
    return True


# ── Review-CLI: den Stapel unbekannter Absender abarbeiten ────────────
#   venv/bin/python -m core.mail review
# Schreibt NUR die lokale Keymap (mail_rules) — kein Netz, keine Passphrase.
# Ein zugewiesener Absender ist ab dem nächsten Poll bekannt und wird
# automatisch in seine Kategorie sortiert.

def _review_cli():
    stack = review_stack(200)
    # Nach normalisiertem Absender bündeln (ein Absender → evtl. viele Mails).
    senders = {}
    for it in stack:
        addr = mail_rules.normalize(it.get("from", ""))
        if not addr:
            continue
        e = senders.setdefault(addr, {"n": 0, "subject": it.get("subject", ""),
                                      "account": it.get("account", "")})
        e["n"] += 1
    if not senders:
        print("Review-Stapel leer — kein unbekannter Absender offen.")
        return 0

    print(f"{len(senders)} unbekannte Absender im Review-Stapel.")
    print("Pro Absender eine Eingabe:")
    print("  • Kategorie-Nummer aus der Liste")
    print("  • ein NEUER Kategoriename  → wird sofort angelegt (z.B. «Reise Zeug»)")
    print("    …Name + ' trash' macht daraus eine Papierkorb-Kategorie")
    print("  • [Enter] = überspringen   •  'q' = Schluss\n")
    for addr, info in senders.items():
        cats = list(mail_rules.categories().keys())
        print("─" * 60)
        print(f"{addr}   ({info['n']} Mail(s), Konto {info['account']})")
        if info["subject"]:
            print(f"   Betreff-Beispiel: «{info['subject'][:60]}»")
        for i, c in enumerate(cats, 1):
            print(f"   [{i}] {c}")
        choice = input("→ Kategorie: ").strip()
        if not choice:
            print("   übersprungen.")
            continue
        if choice.lower() in ("q", "quit", "exit"):
            print("Beende.")
            break
        if choice.isdigit() and 1 <= int(choice) <= len(cats):
            category = cats[int(choice) - 1]
            mail_rules.assign(addr, category)
        else:
            # neuer Name → wird dynamisch angelegt; optionales ' trash'-Suffix
            action = "move"
            parts = choice.rsplit(" ", 1)
            if len(parts) == 2 and parts[1].lower() in ("trash", "move"):
                choice, action = parts[0].strip(), parts[1].lower()
            category = choice
            mail_rules.assign(addr, category, action=action)
        print(f"   ✓ {addr} → {category}")
    print("\nFertig. Künftige Polls sortieren diese Absender automatisch.")
    return 0


# ── Kategorie-Verwaltung (kein Netz, schreibt nur die Keymap) ─────────

def _cats_cli(argv):
    """Kategorien auf Vorrat verwalten — ohne Postfach, ohne Passphrase.

        cats                       -> alle Kategorien + Aktion + Absenderzahl
        addcat "<name>" [trash]    -> neue Kategorie (Default-Aktion move)
        delcat "<name>"            -> Kategorie löschen (Absender -> Review)
    """
    sub = argv[1]
    rest = argv[2:]

    if sub == "cats":
        keymap = mail_rules.keymap()
        used = {}
        for cat in keymap.values():
            used[cat] = used.get(cat, 0) + 1
        print("Kategorien (Absender = wie viele Hände auf diese Kategorie zeigen):\n")
        for name, spec in mail_rules.categories().items():
            tag = "  [System]" if spec.get("system") else ""
            extra = "  auto_future" if spec.get("auto_future") else ""
            print(f"  {name:<22} {spec['action']:<6} "
                  f"{(spec.get('folder') or '—'):<22} "
                  f"Absender={used.get(name, 0)}{tag}{extra}")
        print('\nNeu anlegen:  python -m core.mail addcat "Reise Zeug"')
        print('Als Papierkorb-Kategorie:  python -m core.mail addcat "Werbung" trash')
        return 0

    if sub == "addcat":
        action = "move"
        if rest and rest[-1].lower() in ("move", "trash"):
            action = rest[-1].lower()
            rest = rest[:-1]
        name = " ".join(rest).strip()
        if not name:
            print('Name fehlt. Beispiel:  python -m core.mail addcat "Reise Zeug"')
            return 2
        existed = name in mail_rules.categories()
        spec = mail_rules.ensure_category(name, action=action)
        if existed:
            print(f"Kategorie «{name}» gibt es schon "
                  f"(action={spec['action']}, folder={spec.get('folder')}).")
        else:
            print(f"✓ Kategorie «{name}» angelegt — action={spec['action']}, "
                  f"folder={spec.get('folder')}.")
            print("  Wähle sie ab jetzt im Review per Nummer oder Name.")
        return 0

    if sub == "delcat":
        name = " ".join(rest).strip()
        if not name:
            print('Name fehlt. Beispiel:  python -m core.mail delcat "Reise Zeug"')
            return 2
        try:
            ok, affected = mail_rules.delete_category(name)
        except ValueError as e:
            print(str(e))
            return 2
        if not ok:
            print(f"Kategorie «{name}» gibt es nicht.")
            return 2
        print(f"✓ Kategorie «{name}» gelöscht.")
        if affected:
            print(f"  {affected} Absender sind wieder unbekannt → Review-Stapel.")
        return 0
    return 1


# ── Selftest / Dry-Run-CLI ────────────────────────────────────────────
#   venv/bin/python -m core.mail            -> Rule-Engine-Demo (kein Netz)
#   venv/bin/python -m core.mail review     -> Review-Stapel abarbeiten
#   venv/bin/python -m core.mail cats        -> Kategorien anzeigen
#   venv/bin/python -m core.mail addcat "X" [trash] -> Kategorie anlegen
#   venv/bin/python -m core.mail delcat "X"  -> Kategorie löschen
#   venv/bin/python -m core.mail --poll     -> echter Dry-Run-Poll aller Konten
#   MAIL_DRY_RUN=0 ... --poll               -> LIVE (sortiert wirklich!)

def _selftest():
    import sys
    if "--poll" in sys.argv:
        items = poll_all(dry_run=_dry_run())
        print(f"\n{len(items)} Mail(s) klassifiziert "
              f"({'DRY-RUN' if _dry_run() else 'LIVE'}).")
        return 0
    if len(sys.argv) > 1 and sys.argv[1] in ("cats", "addcat", "delcat"):
        return _cats_cli(sys.argv)
    if "review" in sys.argv[1:]:
        return _review_cli()

    # Reine Logik-Demo. Sie darf die ECHTE Keymap NICHT anfassen — darum den
    # Store für die Dauer der Demo auf eine Wegwerf-Datei umbiegen.
    import tempfile
    mail_rules._STORE = os.path.join(tempfile.mkdtemp(), "mail_rules_demo.json")
    print("Mail-Rule-Engine Selftest (kein Netzwerk, temporäre Keymap)\n")
    mail_rules.assign("rechnung@stadtwerke.de", "zahlen")
    mail_rules.assign("chef@firma.de", "arbeit antworten")
    mail_rules.assign("spam@billig-pillen.ru", "blocken")
    samples = [
        "Stadtwerke <Rechnung@Stadtwerke.de>",   # bekannt -> zahlen
        "Der Chef <chef@firma.de>",              # bekannt -> arbeit
        "spam@billig-pillen.ru",                 # bekannt -> blocken (trash)
        "Neue Newsletter <hallo@unbekannt.com>", # unbekannt -> Review
    ]
    for s in samples:
        cat, known = mail_rules.classify(s)
        spec = mail_rules.category_action(cat)
        print(f"  {mail_rules.normalize(s):<32} -> {cat:<20} "
              f"[{spec['action']}]  {'bekannt' if known else 'NEU → Review'}")
    print("\nKategorien:")
    for name, spec in mail_rules.categories().items():
        print(f"  - {name:<20} action={spec['action']:<6} folder={spec.get('folder')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
