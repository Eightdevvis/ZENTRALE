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
import re
import sys
import ssl
import json
import time
import email
import base64
import imaplib
import smtplib
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, make_msgid, formatdate, parseaddr

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
    # Posteo: Standard-IMAP/SMTP mit normalem Konto-Passwort (kein OAuth, keine
    # App-Passwörter). User = volle Posteo-Adresse, secret = Konto-Passwort.
    "posteo":  {"host": "posteo.de",                "port": 993,  "security": "ssl",
                "verify": True,  "auth": "password"},
}

# Ordner-Prefix für die Kategorie-Ordner, die wir bei Bedarf anlegen.
FOLDER_PREFIX = os.environ.get("MAIL_FOLDER_PREFIX", "ZENTRALE")


def _dry_run():
    return os.environ.get("MAIL_DRY_RUN", "1") not in ("0", "false", "no", "off")


def _action_delay():
    """Pause (Sek.) nach jeder Server-Aktion. Outlook drosselt Bulk-MOVE hart;
    eine kleine Pause hält uns unter der Drossel. 0 schaltet sie ab."""
    try:
        return max(0.0, float(os.environ.get("MAIL_ACTION_DELAY_S", "0.4")))
    except ValueError:
        return 0.4


def _max_reconnect():
    try:
        return max(0, int(os.environ.get("MAIL_MAX_RECONNECT", "5")))
    except ValueError:
        return 5


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


def _touch_poll(name):
    """Merkt sich nur den Zeitpunkt des letzten Polls (kein Watermark mehr —
    die INBOX selbst ist die Arbeitsschlange, siehe poll_account)."""
    with _state_lock:
        data = _load_state()
        acct = data["accounts"].setdefault(name, {})
        acct["last_poll"] = datetime.now().isoformat(timespec="seconds")
        acct.pop("uid_watermark", None)   # alten Stand wegräumen
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


def category_overview():
    """Alle DEFINIERTEN Kategorien mit Anzahl (aus dem letzten 200er-Fenster)
    + Server-Aktion/Ordner. Ebene 1 des Mail-Panels: hier wählt man aus, der
    Review-Stapel ist einfach die Kategorie 'sasha muss gucken' wie jede andere.
    Sortiert: meiste Mails zuerst, dann alphabetisch."""
    cnt = counts()
    out = []
    for name, spec in mail_rules.categories().items():
        out.append({
            "name": name,
            "count": cnt.get(name, 0),
            "action": spec.get("action", "move"),
            "folder": spec.get("folder"),
            "system": bool(spec.get("system")),
        })
    out.sort(key=lambda c: (-c["count"], c["name"].lower()))
    return out


def in_category(name, limit=200):
    """Die Mails einer Kategorie (aus dem letzten 200er-Fenster). Ebene 2 des
    Mail-Panels: Klick auf eine Kategorie zeigt, was drinliegt."""
    return [it for it in recent(200) if it.get("category") == name][:limit]


# ── LIVE aus den echten IMAP-Ordnern (Hybrid-Panel) ──────────────────
# Der lokale Schnappschuss (mail_state.json) hält nur die letzten 200 Mails.
# Für die WAHRE Ordnergröße + den vollen Ordner-Inhalt fragen wir den Server.
# Lesend (STATUS / SELECT readonly / FETCH headers) — throttle-arm, kein MOVE.
# Braucht Passphrase + Konten; ohne → leeres Ergebnis (Aufrufer fällt zurück).

def folder_counts():
    """LIVE: echte Nachrichtenzahl je Kategorie-Ordner (IMAP STATUS), aggregiert
    über alle aktiven Konten. Nur move-Kategorien mit eigenem Ordner — trash-
    Kategorien teilen den Papierkorb und tauchen hier nicht auf. {kat: anzahl}."""
    accts = [a for a in mail_secrets.load_accounts() if a.get("enabled", True)]
    if not accts:
        return {}
    cats = mail_rules.categories()
    out = {}
    for account in accts:
        try:
            with _session(account) as imap:
                for name, spec in cats.items():
                    folder = spec.get("folder")
                    if spec.get("action") != "move" or not folder:
                        continue
                    try:
                        typ, data = imap.status(_q(folder), "(MESSAGES)")
                        if typ == "OK" and data and data[0]:
                            raw = data[0] if isinstance(data[0], bytes) else str(data[0]).encode()
                            m = re.search(rb"MESSAGES\s+(\d+)", raw)
                            if m:
                                out[name] = out.get(name, 0) + int(m.group(1))
                    except _DROP_ERRORS:
                        raise
                    except Exception:
                        pass   # Ordner existiert evtl. noch nicht -> als 0 werten
        except Exception as e:
            state.push_log(f"MAIL: Ordnerzählung fehlgeschlagen — "
                           f"{type(e).__name__}: {e}")
    return out


def _date_key(iso):
    """Sortier-Schlüssel aus einem ISO-Datum (`date` aus _parse_headers). Ordnet
    nach dem ECHTEN Mail-Datum (Date-Header), NICHT nach UID — die UID sagt nach
    einem Verschieben nur »wann einsortiert«, nicht »wann angekommen«. Fehlt oder
    kaputt → ganz alt (sinkt ans Ende der neueste-zuerst-Liste)."""
    if not iso:
        return float("-inf")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:                 # naive → als UTC werten, sonst wirft .timestamp()
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return float("-inf")


def _folder_uids_by_date(imap, limit):
    """UIDs eines (bereits selektierten) Ordners, neueste zuerst. Nutzt server-
    seitiges `UID SORT (REVERSE DATE)` → auch bei >limit Mails kommen die nach
    DATUM neuesten, nicht die zuletzt einsortierten (die hätten die höchsten UIDs,
    nach einem Reconcile aber verwürfelte Daten). Fällt auf UID-Reihenfolge zurück,
    falls der Server SORT nicht kann.

    WICHTIG — SORT nur senden, wenn der Server es in CAPABILITY anbietet:
    **Outlook/Exchange kann KEIN SORT** und quittiert `UID SORT` mit `BAD`.
    Ein paar solcher BADs auf einer gepoolten Verbindung, und Outlook **KAPPT
    die Verbindung** — die unmittelbar folgende `SEARCH`/`FETCH` läuft dann in
    einen `abort` (»Connection closed«), der Ordner kam **leer** zurück bzw. ein
    Body-Read lief in einen `TimeoutError`. Weil hier vorher blind SORT (sogar
    2×, UTF-8 + US-ASCII) pro Öffnen ging, drosselte Outlook nach ~jedem 2.–3.
    Ordner in genau dieses Muster (»Ordner leer« bei jedem x-ten Öffnen). Ohne
    beworbenes SORT also direkt `SEARCH` — kein BAD, keine gekappte Verbindung;
    die Datums-Sortierung macht `folder_mails`/`inbox_tray` ohnehin clientseitig."""
    if "SORT" in getattr(imap, "capabilities", ()):
        for charset in ("UTF-8", "US-ASCII"):
            try:
                typ, data = imap.uid("SORT", "(REVERSE DATE)", charset, "ALL")
                if typ == "OK" and data and data[0]:
                    return [int(u) for u in data[0].split()][:limit]
            except Exception:
                break                         # doch nicht → 1× reicht, dann SEARCH
    typ, data = imap.uid("SEARCH", None, "UID 1:*")
    if typ == "OK" and data and data[0]:
        return sorted((int(u) for u in data[0].split()), reverse=True)[:limit]
    return []


def folder_mails(cat, limit=200):
    """LIVE: die Mails einer Kategorie aus ihrem echten IMAP-Ordner (nur Header).
    trash-Kategorien (kein eigener Ordner) → lokaler Schnappschuss. Liefert
    Liste {account, uid, from, subject, date}, neueste zuerst. [] ohne Key."""
    spec = mail_rules.category_action(cat)
    if spec.get("action") != "move" or not spec.get("folder"):
        return in_category(cat, limit)
    folder = spec["folder"]
    accts = [a for a in mail_secrets.load_accounts() if a.get("enabled", True)]
    out = []
    for account in accts:
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], folder, readonly=True) != "OK":
                    continue
                uids = _folder_uids_by_date(imap, limit)   # neueste nach DATUM zuerst
                if not uids:
                    continue
                # EIN gebündelter FETCH statt pro Mail (throttle-arm).
                typ, fetched = imap.uid(
                    "FETCH", ",".join(str(u) for u in uids),
                    "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if typ != "OK" or not fetched:
                    continue
                for item in fetched:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    meta = item[0].decode("ascii", "replace") if isinstance(item[0], bytes) \
                        else str(item[0])
                    mm = re.search(r"UID\s+(\d+)", meta)
                    hdr = _parse_headers(item[1])
                    out.append({"account": account["name"],
                                "uid": int(mm.group(1)) if mm else None,
                                "from": hdr["from"], "subject": hdr["subject"],
                                "date": hdr["date"]})
        except Exception as e:
            state.push_log(f"MAIL: Ordner '{folder}' lesen — "
                           f"{type(e).__name__}: {e}")
    out.sort(key=lambda x: (_date_key(x["date"]), x["uid"] or 0), reverse=True)
    return out[:limit]


# ── Body lesen + einzelne Mail löschen (Mail-Panel Ebene 2) ──────────

def _part_text(part):
    """Den dekodierten Text eines MIME-Teils als str (best effort)."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, "replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", "replace")


def _strip_html(html):
    """HTML grob zu lesbarem Text (kein echtes Rendering, nur Tags raus)."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_text(msg):
    """Lesbaren Klartext aus einer email.message.Message ziehen: text/plain
    bevorzugt, sonst text/html grob entschärft. Anhänge übersprungen."""
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = _part_text(part)
            elif ctype == "text/html" and html is None:
                html = _part_text(part)
        if plain and plain.strip():
            return plain
        if html:
            return _strip_html(html)
        return ""
    text = _part_text(msg)
    if msg.get_content_type() == "text/html":
        return _strip_html(text)
    return text


# ── Konto-Quarantäne: dauerhaft abgelehnte Logins aussetzen ───────────
# Ein Konto mit falschem Passwort / totem Token lehnt JEDEN Login ab. Ohne
# Bremse liefe jeder Counts-Sweep, jeder Ordner-Abruf und jeder Poll erneut
# dagegen und spammte das Internet-Panel mit »Login abgelehnt«. Darum: nach der
# ersten ENDGÜLTIGEN Ablehnung (auch der eine Token-Refresh-Retry scheiterte)
# das Konto aussetzen — EINMAL loggen, dann für eine Abkühlphase (Default 1 h)
# überspringen. Danach ein stiller neuer Versuch (self-healing, falls Passwort/
# Token inzwischen repariert). `_accounts_for` filtert ausgesetzte Konten, also
# laufen weder die Panel-Ops (`_session`) noch der Poll (`poll_all`) dagegen.
_suspended = {}          # name -> Zeitpunkt der Aussetzung (time.time())
_suspended_lock = threading.Lock()
_SUSPEND_COOLDOWN_S = int(os.environ.get("MAIL_SUSPEND_COOLDOWN_S", "3600"))


def _is_suspended(name):
    """True, solange das Konto in der Abkühlphase ausgesetzt ist. Nach Ablauf
    wird die Aussetzung verworfen → der nächste Zugriff probiert es wieder."""
    if not name:
        return False
    with _suspended_lock:
        ts = _suspended.get(name)
        if ts is None:
            return False
        if time.time() - ts > _SUSPEND_COOLDOWN_S:
            _suspended.pop(name, None)
            return False
        return True


def _suspend_account(name, err):
    """Ein Konto nach endgültig abgelehntem Login aussetzen. Loggt nur beim
    ERSTEN Mal (bzw. nach abgelaufener Abkühlphase) — kein Dauerspam."""
    with _suspended_lock:
        first = name not in _suspended
        _suspended[name] = time.time()
    if first:
        state.push_log(
            f"MAIL [{name}]: Login endgültig abgelehnt ({err}) — Konto "
            f"ausgesetzt (kein weiterer Versuch für {_SUSPEND_COOLDOWN_S // 60} "
            f"min). Fix: Passwort/Token in mail_secrets erneuern oder Konto "
            f"deaktivieren.")


def _accounts_for(account_name=None):
    accts = [a for a in mail_secrets.load_accounts()
             if a.get("enabled", True) and not _is_suspended(a.get("name"))]
    if account_name:
        match = [a for a in accts if a.get("name") == account_name]
        if match:
            return match
    return accts


# ── Body-Cache: einmal geholte Mail-Texte sind unveränderlich ─────────
# Der volle Text einer Mail ändert sich nie — also einmal holen, dann aus dem
# RAM bedienen. Erneutes Öffnen derselben Mail kommt damit ganz ohne Netz aus,
# und ein Prefetch (mail_body der Nachbarn im Hintergrund) macht n/N im Panel
# instant. Größen-begrenzt als simples LRU (älteste fliegen raus).
_body_cache = OrderedDict()      # (account_name, cat, uid) -> body-dict
_body_cache_lock = threading.Lock()
_BODY_CACHE_MAX = int(os.environ.get("MAIL_BODY_CACHE", "128"))


def mail_body(cat, uid, account_name=None):
    """LIVE: vollen Text + Header einer Mail (Cache-aware). Liefert
    {account, uid, from, subject, date, body} oder {error}. Read-only.
    Erfolgreiche Ergebnisse landen im Body-Cache (Mail-Text ist unveränderlich);
    Fehler werden NICHT gecacht (nächster Versuch darf es frisch probieren)."""
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return {"error": "uid ungültig"}
    key = (account_name, cat, uid)
    with _body_cache_lock:
        hit = _body_cache.get(key)
        if hit is not None:
            _body_cache.move_to_end(key)
            return hit
    result = _fetch_body(cat, uid, account_name)
    if isinstance(result, dict) and not result.get("error"):
        with _body_cache_lock:
            _body_cache[key] = result
            _body_cache.move_to_end(key)
            while len(_body_cache) > _BODY_CACHE_MAX:
                _body_cache.popitem(last=False)
    return result


def prefetch_bodies(cat, uids, account_name=None):
    """Mail-Texte der angegebenen uids in den Cache holen (für fire-and-forget
    im Hintergrund-Thread). Überspringt, was schon im Cache liegt — so kostet
    ein Prefetch nichts, wenn der Nutzer eh nicht weiterblättert."""
    spec = mail_rules.category_action(cat)
    if spec.get("action") != "move" or not spec.get("folder"):
        return                       # trash-Kategorie: kein Live-Body, nichts zu tun
    for u in uids:
        try:
            u = int(u)
        except (TypeError, ValueError):
            continue
        with _body_cache_lock:
            if (account_name, cat, u) in _body_cache:
                continue
        try:
            mail_body(cat, u, account_name=account_name)
        except Exception:
            pass                     # Prefetch ist best-effort, nie laut scheitern


def _fetch_body(cat, uid, account_name=None):
    """Den vollen Body EINER Mail wirklich vom Server holen (ohne Cache).
    Der Eingang-Sentinel (`EINGANG`) wird wie der Ordner INBOX behandelt — so
    lässt sich auch aus dem Eingang heraus antworten (das Original liegt dort)."""
    if cat == EINGANG:
        folder = "INBOX"
    else:
        spec = mail_rules.category_action(cat)
        folder = spec.get("folder")
        if spec.get("action") != "move" or not folder:
            return {"error": "kein Live-Ordner für diese Kategorie"}
    for account in _accounts_for(account_name):
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], folder, readonly=True) != "OK":
                    continue
                typ, fetched = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue
                msg = email.message_from_bytes(fetched[0][1])
                try:
                    dt = parsedate_to_datetime(msg.get("Date"))
                    date_s = dt.isoformat() if dt else ""
                except (TypeError, ValueError):
                    date_s = ""
                return {"account": account["name"], "uid": uid,
                        "from": _decode(msg.get("From", "")),
                        "subject": _decode(msg.get("Subject", "")),
                        "date": date_s,
                        "message_id": (msg.get("Message-ID") or "").strip(),
                        "references": (msg.get("References") or "").strip(),
                        "body": _extract_text(msg).strip()}
        except Exception as e:
            state.push_log(f"MAIL: Body '{folder}' uid {uid} — "
                           f"{type(e).__name__}: {e}")
    return {"error": "Mail nicht gefunden"}


def delete_mail(cat, uid, account_name=None):
    """LIVE: eine Mail aus dem Kategorie-Ordner in den Papierkorb verschieben
    (umkehrbar, kein Hard-Expunge). Liefert True bei Erfolg."""
    spec = mail_rules.category_action(cat)
    folder = spec.get("folder")
    if not folder:
        return False
    for account in _accounts_for(account_name):
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], folder, readonly=False) != "OK":
                    continue
                trash = _find_trash(imap)
                if _move_uid(imap, str(uid), trash):
                    state.push_log(f"MAIL: gelöscht (uid {uid}) {folder} → {trash}")
                    return True
        except Exception as e:
            state.push_log(f"MAIL: löschen '{folder}' uid {uid} — "
                           f"{type(e).__name__}: {e}")
    return False


def reassign_sender(sender, category):
    """Den ABSENDER einer Kategorie zuordnen (Keymap-Eintrag). Verschiebt NICHT
    die einzelne Mail — ab jetzt landen KÜNFTIGE Mails dieses Absenders
    automatisch in der neuen Kategorie (Sashas Modell: Absender → Hand → Kat.).
    Liefert (normalisierte_adresse, kategorie)."""
    return mail_rules.assign(sender, category)


def _sortable_folders():
    """Alle Ordner, die als QUELLE eines Umsortierens in Frage kommen: die INBOX
    plus jeder move-Kategorie-Ordner (inkl. Review). Der Papierkorb ist bewusst
    NICHT dabei — ein Keymap-Abgleich soll nie Mail aus dem Papierkorb zurück-
    holen. Dedupliziert (mehrere Kategorien könnten denselben Ordner teilen)."""
    out = ["INBOX"]
    seen = {"INBOX"}
    for spec in mail_rules.categories().values():
        f = spec.get("folder")
        if spec.get("action") == "move" and f and f not in seen:
            out.append(f)
            seen.add(f)
    return out


def refile_sender(sender, category, account_name=None):
    """Sashas Modell ganz: den ABSENDER einer Kategorie zuordnen (Keymap) UND
    **alle** seine vorhandenen Mails dorthin verschieben — egal, wo sie gerade
    liegen.

    KEYMAP-GETRIEBEN (nicht mehr an einer »vorheriger Ordner«-Buchhaltung
    hängend): wir durchsuchen JEDEN sortierbaren Ordner (INBOX + alle move-Ordner,
    inkl. Review) per `SEARCH FROM <absender>` und schieben alle Treffer ins Ziel.
    Der alte Weg las die Herkunft aus classify() VOR dem Umschreiben — sobald die
    Keymap aber schon (z.B. per Bulk/CLI) auf die neue Kategorie zeigte, war
    Quelle == Ziel und es wurde NICHTS bewegt (genau der Bug, durch den bereits
    zugewiesene Absender in Review liegenblieben). Jetzt zählt allein die Keymap:
    Zuweisen ⇒ alle vorhandenen Mails ziehen mit. `sender` darf eine konkrete
    Adresse ODER eine Domain sein (SEARCH FROM matcht als Teilstring).

    Liefert {assigned, category, moved, live, moved_from}. `moved_from` = die
    Ordner, aus denen tatsächlich verschoben wurde. Ohne Key/Konto: nur Keymap."""
    addr, cat = mail_rules.assign(sender, category)
    spec = mail_rules.category_action(cat)
    accts = _accounts_for(account_name)
    if not accts:
        return {"assigned": True, "category": cat, "moved": 0, "live": False,
                "moved_from": []}

    moved = 0
    touched = set()
    for account in accts:
        try:
            with _session(account) as imap:
                folders = _FolderCache()
                target = folders.target(imap, spec)
                for folder in _sortable_folders():
                    if folder == target:
                        continue        # schon am Ziel → nichts zu tun
                    try:
                        if _pselect(imap, account["name"], folder, readonly=False) != "OK":
                            continue
                        typ, data = imap.uid("SEARCH", None, "FROM", '"%s"' % addr)
                        if typ != "OK" or not data or not data[0]:
                            continue
                        # Alle Treffer dieses Ordners in EINEM MOVE (statt pro Mail
                        # ein Roundtrip) → drastisch weniger Outlook-Drossel.
                        n = _move_uid_set(imap, data[0].split(), target)
                        if n:
                            moved += n
                            touched.add(folder)
                    except _DROP_ERRORS:
                        raise
                    except Exception:
                        pass     # Ordner fehlt / nicht durchsuchbar -> überspringen
        except Exception as e:
            state.push_log(f"MAIL: Umsortieren '{addr}' — {type(e).__name__}: {e}")
    state.push_log(f"MAIL: Absender {addr} → {cat} "
                   f"({moved} Mail(s) aus {len(touched)} Ordner(n) umsortiert)")
    return {"assigned": True, "category": cat, "moved": moved, "live": True,
            "moved_from": sorted(touched)}


# ── Eingang: die INBOX als Tray (neu/ungelesen), einsortieren beim Lesen ──
# Sashas Modell: neue Mail bleibt sichtbar in der INBOX, bis er sie liest. Das
# Gelesen-Flag ist der native IMAP-`\Seen` (jeder Client setzt es) — wir bauen
# kein eigenes read/unread. `inbox_tray()` liefert die INBOX mit Gelesen-Flag +
# vermuteter Kategorie; `mark_seen_and_file()` hakt eine Mail ab (setzt `\Seen`
# und sortiert bekannte Absender sofort ein).

_SEEN_RE = re.compile(rb"FLAGS\s*\(([^)]*)\)", re.I)

# Sentinel-„Kategorie" für den Eingang: die TUI/Browser schicken diesen Wert als
# `cat`, wenn eine Mail im Eingang (INBOX) liegt statt in einem Kategorie-Ordner.
# `_fetch_body`/`reply`/`draft` behandeln ihn wie den Ordner INBOX. Muss mit dem
# TUI-Konstanten `MAIL_EINGANG` übereinstimmen.
EINGANG = "__eingang__"


def inbox_tray(limit=200):
    """Die INBOX als Eingang-Tray: {account, uid, from, subject, date, seen,
    known, category}. `seen` aus dem nativen `\\Seen`-Flag, `category` = die per
    Keymap vermutete Zielkategorie (None bei unbekanntem Absender). Neueste
    zuerst. [] ohne Key. Read-only."""
    m = mail_rules.matcher()
    out = []
    for account in _accounts_for():
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], "INBOX", readonly=True) != "OK":
                    continue
                uids = _folder_uids_by_date(imap, limit)   # neueste nach DATUM zuerst
                if not uids:
                    continue
                # EIN gebündelter FETCH: FLAGS (für \Seen) + Header zusammen.
                typ, fetched = imap.uid(
                    "FETCH", ",".join(str(u) for u in uids),
                    "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if typ != "OK" or not fetched:
                    continue
                for item in fetched:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    meta = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
                    mm = re.search(rb"UID\s+(\d+)", meta)
                    fm = _SEEN_RE.search(meta)
                    seen = bool(fm and b"\\seen" in fm.group(1).lower())
                    hdr = _parse_headers(item[1])
                    cat, known = m.classify(hdr["from"])
                    out.append({"account": account["name"],
                                "uid": int(mm.group(1)) if mm else None,
                                "from": hdr["from"], "subject": hdr["subject"],
                                "date": hdr["date"], "seen": seen,
                                "known": known,
                                "category": cat if known else None})
        except Exception as e:
            state.push_log(f"MAIL: Eingang lesen — {type(e).__name__}: {e}")
    out.sort(key=lambda x: (_date_key(x["date"]), x["uid"] or 0), reverse=True)
    return out[:limit]


def mark_seen_and_file(uid, account_name=None):
    """Eine INBOX-Mail abhaken: als gelesen markieren (`\\Seen`) UND, wenn der
    Absender bekannt ist, sofort in seinen Kategorie-Ordner einsortieren (bei
    trash-Kategorien in den Papierkorb). Unbekannter Absender → nur gelesen, die
    Mail bleibt im Eingang, bis er zugeordnet wird. Liefert {seen, filed,
    category, target}."""
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return {"seen": False, "filed": False, "error": "uid ungültig"}
    for account in _accounts_for(account_name):
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], "INBOX", readonly=False) != "OK":
                    continue
                imap.uid("STORE", str(uid), "+FLAGS", "(\\Seen)")
                typ, fetched = imap.uid(
                    "FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                frm = ""
                if typ == "OK" and fetched and isinstance(fetched[0], tuple):
                    frm = _parse_headers(fetched[0][1])["from"]
                cat, known = mail_rules.classify(frm)
                if known:
                    spec = mail_rules.category_action(cat)
                    folders = _FolderCache()
                    target = folders.target(imap, spec)
                    if target and _move_uid(imap, str(uid), target):
                        state.push_log(f"MAIL [{account['name']}] ✓ abgehakt "
                                       f"<{mail_rules.normalize(frm)}> → {cat}")
                        return {"seen": True, "filed": True,
                                "category": cat, "target": target}
                # unbekannt (oder Move abgelehnt): gelesen, bleibt im Eingang
                state.push_log(f"MAIL [{account['name']}] · gelesen, bleibt im "
                               f"Eingang <{mail_rules.normalize(frm)}> "
                               f"({'unbekannt' if not known else 'Move abgelehnt'})")
                return {"seen": True, "filed": False,
                        "category": cat if known else None}
        except Exception as e:
            state.push_log(f"MAIL: abhaken uid {uid} — {type(e).__name__}: {e}")
    return {"seen": False, "filed": False, "error": "nicht gefunden / kein Key"}


def inbox_body(uid, account_name=None):
    """Vollen Text + Header EINER Eingang-Mail (INBOX) lesen. Read-only via
    BODY.PEEK → setzt KEIN `\\Seen` (Lesen im Panel hakt nicht versehentlich ab;
    das macht erst mark_seen_and_file). Liefert {account, uid, from, subject,
    date, body, known, category} oder {error}."""
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return {"error": "uid ungültig"}
    for account in _accounts_for(account_name):
        try:
            with _session(account) as imap:
                if _pselect(imap, account["name"], "INBOX", readonly=True) != "OK":
                    continue
                typ, fetched = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue
                msg = email.message_from_bytes(fetched[0][1])
                try:
                    dt = parsedate_to_datetime(msg.get("Date"))
                    date_s = dt.isoformat() if dt else ""
                except (TypeError, ValueError):
                    date_s = ""
                frm = _decode(msg.get("From", ""))
                cat, known = mail_rules.classify(frm)
                return {"account": account["name"], "uid": uid, "from": frm,
                        "subject": _decode(msg.get("Subject", "")), "date": date_s,
                        "message_id": (msg.get("Message-ID") or "").strip(),
                        "references": (msg.get("References") or "").strip(),
                        "body": _extract_text(msg).strip(),
                        "known": known, "category": cat if known else None}
        except Exception as e:
            state.push_log(f"MAIL: Eingang-Body uid {uid} — {type(e).__name__}: {e}")
    return {"error": "Mail nicht gefunden"}


# ── Reconcile: die Ordner an die Keymap angleichen ───────────────────
# Die Keymap ist die EINZIGE Wahrheit. Ein Reconcile bringt die Server-Ordner
# damit zur Deckung: jede Mail wird über ihren Absender (Trie-Matcher) neu
# klassifiziert und, falls sie im falschen Ordner liegt, in den richtigen
# geschoben. Damit greift »Absender zuweisen ⇒ ALLE vorhandenen Mails ziehen
# nach« lückenlos — auch für Mail, die schon einsortiert war (der Poll schaut
# nur in die INBOX und würde die nie wieder anfassen). Ordner-GETRIEBEN: pro
# Ordner EIN SEARCH + EIN gebündelter Header-FETCH, dann pro Zielordner EIN
# Batch-MOVE — throttle-arm. Der Papierkorb ist keine Quelle (nichts zurück-
# holen). Idempotent: ein zweiter Lauf bewegt nichts mehr.

def _fetch_from_headers(imap, uids, chunk=200):
    """{uid: from-header} für viele uids in wenigen gebündelten FETCHes."""
    out = {}
    for i in range(0, len(uids), chunk):
        part = uids[i:i + chunk]
        typ, fetched = imap.uid("FETCH", ",".join(str(u) for u in part),
                                "(UID BODY.PEEK[HEADER.FIELDS (FROM)])")
        if typ != "OK" or not fetched:
            continue
        for item in fetched:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            meta = item[0].decode("ascii", "replace") if isinstance(item[0], bytes) \
                else str(item[0])
            mm = re.search(r"UID\s+(\d+)", meta)
            if not mm:
                continue
            out[int(mm.group(1))] = _parse_headers(item[1])["from"]
    return out


def reconcile_account(account, dry_run=None):
    """Einen Kontostand an die Keymap angleichen. Liefert
    {account, moved, per_target, dry_run, errors}. Move ist umkehrbar; Dry-Run
    (Default über MAIL_DRY_RUN) fasst nichts an und meldet nur, WAS es täte."""
    if dry_run is None:
        dry_run = _dry_run()
    name = account["name"]
    m = mail_rules.matcher()          # EINMAL bauen, dann pro Mail wiederverwenden
    delay = _action_delay()
    moved = 0
    per_target = {}
    errors = []
    mode = "DRY-RUN" if dry_run else "LIVE"
    state.push_log(f"MAIL [{name}]: Reconcile {mode} — gleiche Ordner an die Keymap an")
    state.push_internet_log(f"IMAP {name} → Reconcile ({mode})")
    try:
        with _session(account) as imap:
            fc = _FolderCache()
            # Zielordner je Kategorie EINMAL auflösen (ensure/Trash-LIST), damit
            # der Inner-Loop pro Mail nur noch ein Dict nachschlägt.
            targets = {}
            for cname, spec in mail_rules.categories().items():
                try:
                    targets[cname] = fc.target(imap, spec)
                except _DROP_ERRORS:
                    raise
                except Exception:
                    pass
            review_target = targets.get(mail_rules.REVIEW)

            for folder in _sortable_folders():
                # Die INBOX ist der Eingang-Tray — sie gehört dem Poll (\Seen-
                # gegatet) und dem Abhaken, NICHT dem Reconcile. Sonst würde ein
                # Abgleich die ungelesene neue Mail vorzeitig aus dem Eingang
                # räumen. Reconcile richtet nur die schon einsortierten Ordner aus.
                if folder == "INBOX":
                    continue
                try:
                    if _pselect(imap, name, folder, readonly=False) != "OK":
                        continue
                    typ, data = imap.uid("SEARCH", None, "UID 1:*")
                    if typ != "OK" or not data or not data[0]:
                        continue
                    uids = [int(u) for u in data[0].split()]
                    from_by_uid = _fetch_from_headers(imap, uids)
                    # uids nach Zielordner gruppieren (nur die, die woanders hin
                    # gehören als in ihren aktuellen Ordner).
                    groups = {}
                    for uid in uids:
                        cat, _known = m.classify(from_by_uid.get(uid, ""))
                        target = targets.get(cat) or review_target
                        if not target or target == folder:
                            continue     # gehört genau hierher → liegen lassen
                        groups.setdefault(target, []).append(uid)
                    for target, guids in groups.items():
                        if dry_run:
                            n = len(guids)
                        else:
                            n = _move_uid_set(imap, guids, target)
                            if delay:
                                time.sleep(delay)   # Drossel-Schutz
                        if n:
                            moved += n
                            per_target[target] = per_target.get(target, 0) + n
                except _DROP_ERRORS:
                    raise
                except Exception as e:
                    errors.append(f"{folder}: {type(e).__name__}: {e}")
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        state.push_log(f"MAIL [{name}]: Reconcile-Fehler — {type(e).__name__}: {e}")
    state.push_log(f"MAIL [{name}]: Reconcile {mode} fertig — "
                   f"{moved} Mail(s) {'würden umsortiert' if dry_run else 'umsortiert'}")
    return {"account": name, "moved": moved, "per_target": per_target,
            "dry_run": dry_run, "errors": errors}


def reconcile_all(dry_run=None):
    """Reconcile über alle aktiven Konten. Liefert Summen + je-Konto-Details."""
    accts = [a for a in mail_secrets.load_accounts() if a.get("enabled", True)]
    if not accts:
        state.push_log("MAIL: Reconcile — keine Konten konfiguriert")
        return {"moved": 0, "accounts": [], "dry_run": _dry_run() if dry_run is None else dry_run}
    results = []
    total = 0
    for acct in accts:
        r = reconcile_account(acct, dry_run=dry_run)
        results.append(r)
        total += r.get("moved", 0)
    return {"moved": total, "accounts": results,
            "dry_run": results[0]["dry_run"] if results else
                       (_dry_run() if dry_run is None else dry_run)}


# ── Antworten senden (SMTP XOAUTH2) ──────────────────────────────────
# Outlook-SMTP mit demselben OAuth-Token wie IMAP (Scope deckt SMTP.Send mit
# ab). Andere Provider können host/port/security/auth übers Konto setzen.
_SMTP_DEFAULTS = {
    "outlook": {"host": "smtp.office365.com", "port": 587,
                "security": "starttls", "auth": "oauth2"},
    "posteo":  {"host": "posteo.de", "port": 465,
                "security": "ssl", "auth": "password"},
    "gmail":   {"host": "smtp.gmail.com", "port": 587,
                "security": "starttls", "auth": "password"},
    "proton":  {"host": "127.0.0.1", "port": 1025,
                "security": "starttls", "auth": "password", "verify": False},
}


def _smtp_cfg(account):
    base = dict(_SMTP_DEFAULTS.get(account.get("provider", ""), {}))
    for k in ("host", "port", "security", "auth", "verify"):
        v = account.get("smtp_" + k)
        if v is not None:
            base[k] = v
    return base


def _compose_message(from_addr, to_addr, subject, body, in_reply_to=None,
                     references=None):
    """Eine (Antwort-)Mail als email.message bauen — gemeinsam von Senden (SMTP)
    und Entwurf-Speichern (IMAP Drafts) genutzt, damit Threading/Header identisch
    sind."""
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references or in_reply_to)
    msg.set_content(body or "")
    return msg


def send_reply(account, to_addr, subject, body, in_reply_to=None, references=None):
    """Eine (Antwort-)Mail über SMTP senden. Bei oauth2 via XOAUTH2 mit dem
    frischen Access-Token (kein Passwort). Setzt In-Reply-To/References fürs
    Threading. Liefert True; wirft bei Fehler (Aufrufer fängt)."""
    cfg = _smtp_cfg(account)
    if not cfg.get("host"):
        raise RuntimeError(f"kein SMTP-Host für Provider '{account.get('provider')}'")
    user = account["user"]

    msg = _compose_message(user, to_addr, subject, body, in_reply_to, references)

    host, port = cfg["host"], int(cfg.get("port", 587))
    security = cfg.get("security", "starttls")
    ctx = ssl.create_default_context()
    if cfg.get("verify") is False:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    state.push_log(f"MAIL [{account['name']}]: SMTP {host}:{port} → senden")
    state.push_internet_log(f"SMTP {account['name']} → {host}:{port}")

    if security == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
    try:
        smtp.ehlo()
        if security == "starttls":
            smtp.starttls(context=ctx)
            smtp.ehlo()
        if cfg.get("auth") == "oauth2":
            import mail_oauth
            token = mail_oauth.access_token_for(account)
            xo = f"user={user}\x01auth=Bearer {token}\x01\x01"
            code, resp = smtp.docmd(
                "AUTH", "XOAUTH2 " + base64.b64encode(xo.encode("utf-8")).decode("ascii"))
            if code == 334:                      # Server will Detail -> leere Zeile, dann Fehler
                code, resp = smtp.docmd("")
            if code != 235:
                raise RuntimeError(f"SMTP XOAUTH2 abgelehnt: {code} {resp!r}")
        else:
            smtp.login(user, account["secret"])
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    state.push_log(f"MAIL [{account['name']}]: ✓ Antwort an {to_addr} gesendet")
    return True


def _find_drafts(imap):
    """Entwürfe-Ordner über das SPECIAL-USE-Attribut \\Drafts finden, sonst
    raten (Outlook/Exchange nennt ihn üblicherweise 'Drafts')."""
    for line in _list_folders(imap):
        if "\\drafts" in line.lower():
            name = _list_name(line)
            if name:
                return name
    return "Drafts"


def save_draft(account, to_addr, subject, body, in_reply_to=None, references=None):
    """Eine (Antwort-)Mail als ENTWURF in den Drafts-Ordner des Kontos legen
    (IMAP APPEND mit \\Draft-Flag) — KEIN SMTP, nichts geht raus. Threading/Header
    identisch zum Senden, damit der Entwurf in Outlook/Handy sauber im Thread
    hängt. Liefert den Ordnernamen. Wirft bei Fehler (Aufrufer fängt)."""
    msg = _compose_message(account["user"], to_addr, subject, body,
                           in_reply_to, references)
    with _session(account) as imap:
        drafts = _ensure_folder(imap, _find_drafts(imap))
        typ, _ = imap.append(_q(drafts), r"(\Draft)",
                             imaplib.Time2Internaldate(time.time()),
                             msg.as_bytes())
        if typ != "OK":
            raise RuntimeError(f"APPEND in '{drafts}' abgelehnt: {typ}")
    state.push_log(f"MAIL [{account['name']}]: ✎ Entwurf in '{drafts}' gespeichert")
    return drafts


def _file_inbox_after_reply(uid, account_name):
    """Nach einer Antwort/einem Entwurf AUS DEM EINGANG die Original-Mail abhaken
    (gelesen + einsortieren) — der Nutzer hat sie ja bearbeitet, sie muss nicht
    mehr im Eingang liegen. Best-effort: klappt das Einsortieren nicht (unbekannter
    Absender bleibt liegen, Move abgelehnt …), ist die Antwort trotzdem raus."""
    try:
        return mark_seen_and_file(uid, account_name=account_name)
    except Exception as e:
        state.push_log(f"MAIL: auto-einsortieren nach Antwort uid {uid} — "
                       f"{type(e).__name__}: {e}")
        return {"seen": False, "filed": False, "error": str(e)}


def draft_reply(cat, uid, body, account_name=None):
    """Wie reply_to_mail, aber die getippte Antwort wird als ENTWURF in den
    Drafts-Ordner gelegt statt gesendet. Liefert {ok, to, subject, folder}/{error}.
    Aus dem Eingang heraus wird die Original-Mail danach auto-einsortiert."""
    info = mail_body(cat, uid, account_name=account_name)
    if not isinstance(info, dict) or info.get("error"):
        return {"error": (info or {}).get("error", "Original nicht ladbar")}
    accts = _accounts_for(account_name or info.get("account"))
    if not accts:
        return {"error": "kein Konto / kein Key"}
    account = accts[0]
    to_addr = parseaddr(info.get("from", ""))[1] or info.get("from", "")
    subj = info.get("subject", "") or ""
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    refs = (info.get("references", "") + " " + info.get("message_id", "")).strip()
    try:
        folder = save_draft(account, to_addr, subj, body,
                            in_reply_to=info.get("message_id") or None,
                            references=refs or None)
        res = {"ok": True, "to": to_addr, "subject": subj, "folder": folder,
               "draft": True}
        if cat == EINGANG:
            res["filed"] = _file_inbox_after_reply(uid, account["name"])
        return res
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def reply_to_mail(cat, uid, body, account_name=None):
    """Komfort-Wrapper fürs Panel: holt die Original-Mail (Absender, Betreff,
    Message-ID) und sendet die getippte Antwort dorthin. Liefert {ok}/{error}.
    Aus dem Eingang heraus wird die Original-Mail danach auto-einsortiert
    (`filed` im Ergebnis)."""
    info = mail_body(cat, uid, account_name=account_name)
    if not isinstance(info, dict) or info.get("error"):
        return {"error": (info or {}).get("error", "Original nicht ladbar")}
    accts = _accounts_for(account_name or info.get("account"))
    if not accts:
        return {"error": "kein Konto / kein Key"}
    account = accts[0]
    to_addr = parseaddr(info.get("from", ""))[1] or info.get("from", "")
    subj = info.get("subject", "") or ""
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    refs = (info.get("references", "") + " " + info.get("message_id", "")).strip()
    try:
        send_reply(account, to_addr, subj, body,
                   in_reply_to=info.get("message_id") or None,
                   references=refs or None)
        res = {"ok": True, "to": to_addr, "subject": subj}
        if cat == EINGANG:
            res["filed"] = _file_inbox_after_reply(uid, account["name"])
        return res
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


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


def _connect(account, force_token=False):
    cfg = _provider_cfg(account)
    host, port = cfg["host"], int(cfg["port"])
    # Socket-Timeout, damit eine tote (poolte) Verbindung nicht ewig hängt —
    # ein NOOP/FETCH auf einem halb-toten Socket gibt dann auf statt zu blocken.
    timeout = int(os.environ.get("MAIL_NET_TIMEOUT_S", "30"))
    if cfg.get("security") == "ssl":
        ctx = ssl.create_default_context()
        if not cfg.get("verify", True):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=timeout)
    else:
        imap = imaplib.IMAP4(host, port, timeout=timeout)
        if cfg.get("security") == "starttls":
            ctx = ssl.create_default_context()
            if not cfg.get("verify", True):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            imap.starttls(ssl_context=ctx)

    if cfg.get("auth") == "oauth2":
        # XOAUTH2: frisches Access-Token holen (Refresh über den gespeicherten
        # refresh_token, core/mail_oauth.py). Token NIE persistiert, nur im RAM.
        # `force_token` erzwingt ein neues Token (Retry, wenn das gecachte
        # abgelehnt wurde). Scheitert die Auth, den Socket sauber schließen,
        # damit der Aufrufer mit frischer Verbindung neu ansetzen kann.
        import mail_oauth
        user = account["user"]
        token = mail_oauth.access_token_for(account, force_refresh=force_token)
        auth_str = f"user={user}\x01auth=Bearer {token}\x01\x01"
        try:
            imap.authenticate("XOAUTH2", lambda _=None: auth_str.encode("utf-8"))
        except Exception:
            try:
                imap.logout()
            except Exception:
                pass
            raise
    else:
        imap.login(account["user"], account["secret"])
    # Opt-in IMAP-Protokoll-Mitschnitt für die Fehlersuche. ERST NACH der
    # Authentifizierung setzen, damit das XOAUTH2-Token NICHT mitgeloggt wird.
    if os.environ.get("MAIL_IMAP_DEBUG") == "1":
        imap.debug = 4
    return imap


# ── Verbindungs-Pool: warme IMAP-Verbindungen wiederverwenden ─────────
# Früher baute JEDE Lese-/Schreib-Operation (counts/folder/body/delete/assign)
# eine FRISCHE TLS-Verbindung auf, meldete sich per XOAUTH2 an und loggte sich
# danach wieder aus. Bei Outlook kostet allein dieses Handshake ~1-3 s — und
# zwar pro Kategorie-Klick, pro geöffneter Mail, pro n/N. Genau das machte das
# Panel zäh. Der Pool hält pro Konto EINE Verbindung warm und reicht sie wieder
# her; ein Lock pro Konto serialisiert den Zugriff (imaplib ist nicht
# thread-safe). Stirbt die Verbindung (Idle-Timeout des Servers, Outlook-
# Drossel-EOF), fliegt sie raus und der nächste Borrow baut transparent neu auf.
# Der Bulk-Poll (poll_account) und SMTP bleiben bewusst außen vor — die haben
# eigene, langlebige Verbindungs-/Reconnect-Logik.
_pool = {}            # name -> warmes imaplib-Objekt
_pool_selected = {}   # name -> (folder, readonly) zuletzt selektiert (skip SELECT)
_pool_locks = {}      # name -> threading.Lock (serialisiert Zugriff pro Konto)
_pool_guard = threading.Lock()


def _pool_lock_for(name):
    with _pool_guard:
        lk = _pool_locks.get(name)
        if lk is None:
            lk = _pool_locks[name] = threading.Lock()
        return lk


def _alive(imap):
    """Billiger Lebens-Check: ein NOOP-Roundtrip statt voller TLS+Auth."""
    try:
        return imap.noop()[0] == "OK"
    except Exception:
        return False


def _drop_conn(name, imap=None):
    """Verbindung aus dem Pool werfen (nach Bruch / am Lebensende)."""
    _pool.pop(name, None)
    _pool_selected.pop(name, None)
    if imap is not None:
        try:
            imap.logout()
        except Exception:
            pass


@contextmanager
def _session(account):
    """Borgt eine warme IMAP-Verbindung fürs Konto (verbindet bei Bedarf neu).
    Pro Konto serialisiert; bricht die Verbindung weg, fliegt sie aus dem Pool
    und der nächste Borrow baut frisch auf."""
    name = account["name"]
    with _pool_lock_for(name):
        imap = _pool.get(name)
        if imap is None or not _alive(imap):
            _drop_conn(name, imap)
            try:
                imap = _connect(account)
            except imaplib.IMAP4.error as e:
                # Der Server hat das (gecachte) Access-Token abgelehnt
                # (AUTHENTICATIONFAILED — früh invalidiert / Uhr-Skew). Standard-
                # OAuth-Retry: EINMAL mit erzwungenem Token-Refresh frisch
                # verbinden, statt die ganze Operation fallen zu lassen.
                state.push_log(f"MAIL [{name}]: Login abgelehnt ({e}) — Token "
                               f"erneuern, 1× neu verbinden")
                try:
                    imap = _connect(account, force_token=True)
                except imaplib.IMAP4.error as e2:
                    # Auch mit frischem Token abgelehnt → der Login ist endgültig
                    # kaputt (falsches Passwort / toter refresh_token). Konto
                    # aussetzen, statt es bei jedem Sweep/Poll neu zu versuchen.
                    _suspend_account(name, e2)
                    raise
            _pool[name] = imap
        try:
            yield imap
        except _DROP_ERRORS:
            _drop_conn(name, imap)
            raise


def _pselect(imap, name, folder, readonly=True):
    """SELECT mit Gedächtnis: ist der Ordner schon im gewünschten Modus aktiv,
    sparen wir den Roundtrip (n/N im selben Ordner → nur noch FETCH). Liefert
    den IMAP-Status-String ('OK' / sonst)."""
    key = (folder, readonly)
    if _pool_selected.get(name) == key:
        return "OK"
    typ, _ = imap.select(_q(folder), readonly=readonly)
    if typ == "OK":
        _pool_selected[name] = key
    else:
        _pool_selected.pop(name, None)
    return typ


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


# LIST-Antwort:  (flags) "sep" name   — der Name ist ENTWEDER ein gequoteter
# String "..." ODER ein Atom ohne Leerzeichen. Der Separator ist selbst gequotet
# ("/" oder NIL) — naives split('"')[-2] erwischt deshalb bei UNgequoteten Namen
# den Separator statt den Ordnernamen. Darum sauber per Regex.
_LIST_RE = re.compile(r'^\([^)]*\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(.+?)\s*$')


def _list_name(line):
    """Liefert den Mailbox-Namen aus einer LIST-Zeile (oder None)."""
    m = _LIST_RE.match(line)
    if not m:
        return None
    name = m.group(1)
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return name


def _find_trash(imap):
    """Papierkorb über das SPECIAL-USE-Attribut \\Trash finden, sonst raten."""
    for line in _list_folders(imap):
        if "\\trash" in line.lower():
            name = _list_name(line)
            if name:
                return name
    # Kein \Trash gefunden -> Exchange/Outlook nennt ihn üblicherweise so:
    return "Deleted Items"


def _ensure_folder(imap, name):
    """Legt einen Ordner an, falls er fehlt (idempotent)."""
    existing = set()
    for line in _list_folders(imap):
        n = _list_name(line)
        if n:
            existing.add(n)
    if name not in existing:
        try:
            # MUSS gequotet werden: ohne Anführungszeichen zerlegt IMAP einen
            # Ordnernamen mit Leerzeichen ("Job Opportunities") in zwei Argumente
            # -> CREATE scheitert, der spätere MOVE wird "abgelehnt".
            imap.create(_q(name))
        except Exception:
            pass
    return name


def _target_folder(imap, action_spec):
    if action_spec.get("action") == "trash":
        return _find_trash(imap)
    folder = action_spec.get("folder") or f"{FOLDER_PREFIX}/Review"
    return _ensure_folder(imap, folder)


class _FolderCache:
    """Löst Zielordner EINMAL auf statt pro Mail. Jede Ordner-Auflösung kostet
    sonst ein volles LIST am Server — bei hunderten Mails ein Befehls-Sturm,
    den Outlook mit Throttling/Verbindungsabbruch quittiert. Der Cache überlebt
    auch Reconnects (Ordnernamen sind stabil, einmal angelegt bleibt angelegt).
    """
    def __init__(self):
        self._trash = None
        self._ensured = set()

    def target(self, imap, spec):
        if spec.get("action") == "trash":
            if self._trash is None:
                self._trash = _find_trash(imap)
            return self._trash
        folder = spec.get("folder") or f"{FOLDER_PREFIX}/Review"
        if folder not in self._ensured:
            _ensure_folder(imap, folder)
            self._ensured.add(folder)
        return folder


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


def _move_uid_set(imap, uids, target, chunk=200):
    """Mehrere UIDs in EINEM Rutsch nach `target` verschieben statt pro Mail ein
    eigener Roundtrip (das war der Grund, warum Einsortieren so lange dauerte —
    ein Absender mit 40 alten Mails = 40 sequentielle MOVEs an Outlook, das dabei
    drosselt). `UID MOVE` mit Sequenz-Set; Fallback COPY+\\Deleted+EXPUNGE. In
    Blöcken (`chunk`), damit die Kommandozeile nicht zu lang wird. Liefert die
    Zahl erfolgreich verschobener Mails."""
    uset_all = [u.decode() if isinstance(u, bytes) else str(u) for u in uids]
    if not uset_all:
        return 0
    has_move = b"MOVE" in (imap.capabilities or ())
    moved = 0
    for i in range(0, len(uset_all), chunk):
        part = uset_all[i:i + chunk]
        uset = ",".join(part)
        if has_move:
            typ, _ = imap.uid("MOVE", uset, _q(target))
            if typ == "OK":
                moved += len(part)
                continue
        typ, _ = imap.uid("COPY", uset, _q(target))
        if typ != "OK":
            continue
        imap.uid("STORE", uset, "+FLAGS", "(\\Deleted)")
        imap.expunge()
        moved += len(part)
    return moved


def _q(name):
    # IMAP-Mailbox-Name quoten (Ordner mit Leer-/Sonderzeichen).
    return '"' + name.replace('"', '\\"') + '"'


# ── Ein Konto pollen ──────────────────────────────────────────────────

# Verbindungs-Abbrüche, bei denen ein Reconnect sinnvoll ist. Outlook wirft
# bei Bulk-MOVE-Drosselung ein hartes EOF -> imaplib.IMAP4.abort.
_DROP_ERRORS = (imaplib.IMAP4.abort, ssl.SSLError, OSError, EOFError)


def _handle_uid(imap, name, uid, dry_run, folders, results, seen=False):
    """Eine INBOX-Mail: FETCHen, klassifizieren, (live) einsortieren — ABER nur,
    wenn sie GELESEN (`\\Seen`) UND der Absender BEKANNT ist. Sonst bleibt sie im
    Eingang (INBOX) liegen: ungelesenes zeigt sich Sasha erst, unbekanntes wartet
    auf eine Zuordnung. Liefert (abgehakt?, verschoben?): abgehakt=True heißt 'in
    diesem Lauf nicht nochmal anfassen' (einsortiert ODER bewusst liegengelassen
    ODER nicht abrufbar); verschoben=True nur bei erfolgreichem Live-Move.
    `_DROP_ERRORS` propagieren nach oben und lösen einen Reconnect aus."""
    typ, fetched = imap.uid("FETCH", str(uid),
                            "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
    if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
        return True, False  # nicht lesbar -> abhaken, nicht ewig wiederholen
    hdr = _parse_headers(fetched[0][1])
    category, known = mail_rules.classify(hdr["from"])
    spec = mail_rules.category_action(category)

    # Einsortieren erst, wenn GELESEN und BEKANNT (Sashas Eingang-Modell). Alles
    # andere bleibt im Eingang; der nächste Poll prüft es erneut (selbstheilend).
    should_file = known and seen

    item = {
        "account": name,
        "uid": uid,
        "from": hdr["from"],
        "subject": hdr["subject"],
        "date": hdr["date"],
        "category": category,
        "known": known,
        "seen": seen,
        "action": spec.get("action", "move"),
        "applied": False,
        "dry_run": dry_run,
        "seen_at": datetime.now().isoformat(timespec="seconds"),
    }

    done, moved = True, False
    if should_file and not dry_run:
        target = folders.target(imap, spec)   # Drop-Fehler hier -> Reconnect
        if _move_uid(imap, uid, target):
            item["applied"] = True
            item["target"] = target
            moved = True
            state.push_log(f"MAIL [{name}] ✓ «{hdr['subject'][:48]}» "
                           f"<{mail_rules.normalize(hdr['from'])}> → {category}")
        else:
            done = False                       # Move abgelehnt -> nächster Poll
            state.push_log(f"MAIL [{name}]: Move abgelehnt (uid {uid}) → {target}")
    elif should_file and dry_run:
        state.push_log(f"MAIL [{name}] · «{hdr['subject'][:48]}» "
                       f"<{mail_rules.normalize(hdr['from'])}> → {category} (würde)")
    # ungelesen/unbekannt → still im Eingang lassen (kein Log-Spam pro Poll)

    _record(item)
    results.append(item)
    return done, moved


def poll_account(account, dry_run=None):
    """Holt neue Mails eines Kontos, klassifiziert + (optional) sortiert.

    Robust gegen Verbindungs-Abbrüche: Outlook drosselt Bulk-MOVE und kappt
    dann die TLS-Verbindung (EOF). Wir fangen das ab, verbinden neu und machen
    weiter — gefahrlos, weil verschobene Mails die INBOX verlassen, ein erneutes
    SEARCH sie also nicht wieder einsammelt. Liefert die klassifizierten Items.
    """
    if dry_run is None:
        dry_run = _dry_run()
    name = account["name"]
    cfg = _provider_cfg(account)
    mode = "DRY-RUN" if dry_run else "LIVE"
    state.push_log(f"MAIL [{name}]: poll {cfg['host']}:{cfg['port']} ({mode})")
    state.push_internet_log(f"IMAP {name} → {cfg['host']}:{cfg['port']} ({mode})")

    delay = _action_delay()
    folders = _FolderCache()        # Ordner einmal auflösen (überlebt Reconnects)
    results = []
    processed = set()               # in DIESEM Lauf schon abgehakte UIDs
    applied = set()                 # davon erfolgreich verschoben
    attempt = 0

    # Kein Watermark mehr: die INBOX IST die Arbeitsschlange. Sortierte Mails
    # verlassen die INBOX (move/trash), ein erneutes SEARCH sammelt sie also
    # nicht wieder ein. Abgelehnte/offene Mails bleiben liegen und werden beim
    # nächsten Poll erneut versucht — selbstheilend, ohne dass ein Watermark
    # tieferliegende UIDs verwaisen lässt.
    while True:
        imap = None
        try:
            imap = _connect(account)
            imap.select("INBOX")
            # Alles, was aktuell in der INBOX liegt (und in diesem Lauf noch
            # nicht behandelt wurde). Outlook lehnt `UID SEARCH ALL` mit
            # "Command Argument Error" ab, akzeptiert aber den UID-Bereich
            # `1:*` — und 1 liegt nie über der höchsten UID, anders als ein
            # Watermark-Startpunkt. `*` ist die höchste vorhandene UID.
            typ, data = imap.uid("SEARCH", None, "UID 1:*")
            uids = []
            if typ == "OK" and data and data[0]:
                for u in data[0].split():
                    u = int(u)
                    if u not in processed:
                        uids.append(u)
            uids.sort()
            if not uids:
                if not processed:
                    state.push_log(f"MAIL [{name}]: INBOX leer — nichts zu tun")
                break

            # Gelesen-Status (Eingang-Modell): nur GELESENE bekannte Mail verlässt
            # die INBOX. `SEARCH SEEN` liefert die gelesenen UIDs in einem Rutsch.
            typ_s, sdata = imap.uid("SEARCH", None, "SEEN")
            seen_uids = set()
            if typ_s == "OK" and sdata and sdata[0]:
                seen_uids = {int(u) for u in sdata[0].split()}

            for uid in uids:
                done, moved = _handle_uid(imap, name, uid, dry_run, folders,
                                          results, seen=(uid in seen_uids))
                processed.add(uid)
                if moved:
                    applied.add(uid)
                if delay and not dry_run:
                    time.sleep(delay)          # Drossel-Schutz zwischen Aktionen
            break                              # alle erledigt

        except _DROP_ERRORS as e:
            attempt += 1
            if attempt > _max_reconnect():
                state.push_log(f"MAIL [{name}]: zu viele Abbrüche ({type(e).__name__}) "
                               f"— Rest beim nächsten Poll.")
                break
            wait = min(2 ** attempt, 30)
            state.push_log(f"MAIL [{name}]: Verbindung abgebrochen "
                           f"({type(e).__name__}) — neu verbinden in {wait}s "
                           f"(Versuch {attempt}/{_max_reconnect()})")
            time.sleep(wait)
            continue                           # weiter mit dem INBOX-Rest
        except imaplib.IMAP4.error as e:
            # Login abgelehnt (kein .abort — das fängt _DROP_ERRORS oben ab):
            # falsches Passwort / toter Token. Konto aussetzen, damit der Poll
            # (und die Panel-Ops) nicht bei jedem Lauf erneut dagegenlaufen.
            _suspend_account(name, e)
            break
        except Exception as e:
            state.push_log(f"MAIL [{name}]: Poll-Fehler — {type(e).__name__}: {e}")
            break
        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:
                    pass

    if not dry_run:
        _touch_poll(name)
        if processed:
            state.push_log(f"MAIL [{name}]: {len(applied)}/{len(processed)} gelesene "
                           f"Mail(s) einsortiert, {len(processed) - len(applied)} "
                           f"bleiben im Eingang (ungelesen/unbekannt)")
    return results


def poll_all(dry_run=None):
    accounts = _accounts_for()          # ausgesetzte (Login abgelehnt) fallen raus
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

def _probe_cli():
    """Diagnose: verbindet, selektiert INBOX und probiert mehrere SEARCH-Formen
    durch — zeigt für jede die ROHE Server-Antwort. So sehen wir genau, was
    Outlook akzeptiert, statt zu raten. Kein Schreibzugriff, nur Lesen.
    """
    accounts = [a for a in mail_secrets.load_accounts() if a.get("enabled", True)]
    if not accounts:
        print("keine Konten konfiguriert")
        return 1
    for account in accounts:
        name = account["name"]
        print(f"\n=== {name} ===")
        imap = _connect(account)
        try:
            typ, data = imap.select("INBOX")
            print(f"SELECT INBOX           -> {typ} {data}")
            try:
                print(f"STATUS                 -> "
                      f"{imap.status('INBOX', '(MESSAGES UIDNEXT UIDVALIDITY)')}")
            except Exception as e:
                print(f"STATUS                 -> FEHLER {type(e).__name__}: {e}")

            variants = [
                ("search(None,'ALL')      [seq]", lambda: imap.search(None, "ALL")),
                ("uid('SEARCH','ALL')          ", lambda: imap.uid("SEARCH", "ALL")),
                ("uid('SEARCH',None,'ALL')     ", lambda: imap.uid("SEARCH", None, "ALL")),
                ("uid('SEARCH','UID','1:*')    ", lambda: imap.uid("SEARCH", "UID", "1:*")),
                ("uid('SEARCH',None,'UID 1:*') ", lambda: imap.uid("SEARCH", None, "UID 1:*")),
                ("uid('SEARCH','1:*')          ", lambda: imap.uid("SEARCH", "1:*")),
            ]
            for label, fn in variants:
                try:
                    typ, data = fn()
                    n = len(data[0].split()) if (data and data[0]) else 0
                    print(f"{label} -> {typ}  ({n} Treffer)")
                except Exception as e:
                    print(f"{label} -> FEHLER {type(e).__name__}: {e}")
        finally:
            try:
                imap.logout()
            except Exception:
                pass
    return 0


def _test_cli(argv):
    """Login-Test eines (oder aller) Konten: zeigt User/Host und ob der IMAP-
    Login klappt. Read-only. Aufruf: `python core/mail.py test [name]`."""
    name = argv[2] if len(argv) > 2 else None
    accts = mail_secrets.load_accounts()
    if name:
        accts = [a for a in accts if a.get("name") == name]
    if not accts:
        print("kein passendes Konto." if name else
              "keine Konten (Passphrase/Keyring da?).")
        return 1
    rc = 0
    for a in accts:
        cfg = _provider_cfg(a)
        print(f"\n=== {a.get('name')} ({a.get('provider')}) ===")
        print(f"  user   : {a.get('user')!r}")     # repr zeigt versteckte Zeichen
        print(f"  host   : {cfg.get('host')}:{cfg.get('port')} "
              f"{cfg.get('security')} auth={cfg.get('auth')}")
        if a.get("auth") != "oauth2":
            print(f"  secret : {len(a.get('secret',''))} Zeichen")
        imap = None
        try:
            imap = _connect(a)
            typ, _ = imap.select("INBOX")
            print(f"  LOGIN  : OK  (INBOX select {typ})")
        except Exception as e:
            print(f"  LOGIN  : FEHLER — {e!r}")
            rc = 1
        finally:
            if imap is not None:
                try:
                    imap.logout()
                except Exception:
                    pass
    return rc


def _selftest():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        return _test_cli(sys.argv)
    if "--probe" in sys.argv:
        return _probe_cli()
    if "--poll" in sys.argv:
        items = poll_all(dry_run=_dry_run())
        print(f"\n{len(items)} Mail(s) klassifiziert "
              f"({'DRY-RUN' if _dry_run() else 'LIVE'}).")
        return 0
    if "reconcile" in sys.argv[1:]:
        # Ordner an die Keymap angleichen (bereits einsortierte Mail nachziehen).
        # Default DRY-RUN — zeigt nur die Umsortier-Absicht; MAIL_DRY_RUN=0 = LIVE.
        res = reconcile_all(dry_run=_dry_run())
        mode = "DRY-RUN" if res["dry_run"] else "LIVE"
        print(f"\nReconcile {mode}: {res['moved']} Mail(s) "
              f"{'würden umsortiert' if res['dry_run'] else 'umsortiert'}.")
        for acc in res["accounts"]:
            print(f"  [{acc['account']}] {acc['moved']} → " +
                  (", ".join(f"{t}:{n}" for t, n in acc["per_target"].items()) or "—"))
            for err in acc["errors"]:
                print(f"     ! {err}")
        if res["dry_run"]:
            print("\n(nichts angefasst — MAIL_DRY_RUN=0 … reconcile macht es LIVE)")
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
