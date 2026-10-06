# ui/routen/mail.py
#
# Mail-Triage: Panel, Zähl- und Ordner-Caches, Live-Poll, Lesen/Antworten/Sortieren.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import json
import os
import threading    # für den Hintergrund-Poll (blockiert den Request nicht)
import time         # für das Alter des Live-Ordnerzähl-Caches
from flask import Blueprint, jsonify, request

import mail         # type: ignore  – Mail-Triage (read-only Panel + Live-Poll)
import mail_secrets # type: ignore  – verschlüsselter Zugangsdaten-Speicher
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

from ui.routen.gemeinsam import _DATA_DIR

bp = Blueprint('mail', __name__)


# ── Mail-Triage (read-only Panel + expliziter Live-Poll) ────────────────
# Das Panel selbst ist KEY-FREI: Kategorie-Übersicht + Mails lesen nur den
# lokalen Triage-Stand (data/mail_state.json, unverschlüsselt). Die Passphrase
# (Env ODER OS-Keyring) braucht NUR der Live-Poll, der echte IMAP-Aktionen tut.

_mail_poll_lock = threading.Lock()
_mail_poll_running = {"on": False}

_mail_reconcile_lock = threading.Lock()
_mail_reconcile_running = {"on": False}

# Cache der LIVE-Ordnerzählung (IMAP STATUS). Wird nicht-blockierend im
# Hintergrund aufgefrischt (POST /api/mail/refresh-counts) und von /api/mail
# nur GELESEN — so bleibt das Panel schnell, während die echten Zahlen
# nachtröpfeln. {kat: anzahl}; leer, solange noch nie/ohne Key aufgefrischt.
# PERSISTIERT auf Disk (data/mail_counts.json): sonst zeigt das Panel nach jedem
# Backend-Neustart erst den mageren lokalen Schnappschuss (nur letzte ~200 Mails
# → z.B. „171") und muss die echten Zahlen (z.B. 1000+) neu ersweepen. Mit
# Persistenz stehen die letzten ECHTEN Zahlen sofort da; die TTL frischt sie
# danach im Hintergrund einmal auf.
_mail_live = {"counts": {}, "ts": 0.0, "refreshing": False}
_mail_live_lock = threading.Lock()
_MAIL_COUNTS_FILE = os.path.join(_DATA_DIR, "mail_counts.json")


def _mail_counts_load():
    """Zuletzt persistierte Live-Zahlen beim Start in den Cache holen (best
    effort — fehlt/kaputt die Datei, bleibt der Cache einfach leer)."""
    try:
        with open(_MAIL_COUNTS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("counts"), dict):
            _mail_live["counts"] = d["counts"]
            _mail_live["ts"] = float(d.get("ts") or 0.0)
    except Exception:
        pass


def _mail_counts_save():
    """Den frischen Zähl-Stand atomar auf Disk schreiben (überlebt Neustart)."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = _MAIL_COUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"counts": _mail_live["counts"], "ts": _mail_live["ts"]},
                      f, ensure_ascii=False)
        os.replace(tmp, _MAIL_COUNTS_FILE)
    except Exception as e:
        state.push_log(f"MAIL: Zähl-Cache speichern — {type(e).__name__}: {e}")


_mail_counts_load()


# ── Ordner-Inhalts-Cache (Header-Listen je Kategorie) ────────────────────
# Jeder Ordner-Aufruf machte bisher einen vollen IMAP SELECT+SEARCH+FETCH → das
# spürbare „lädt ordner…" bei JEDEM Öffnen. Jetzt: den Inhalt je Kategorie cachen,
# beim Öffnen SOFORT aus dem Cache liefern und (erst wenn abgelaufen) im Hinter-
# grund auffrischen. Persistiert auf Disk (data/mail_folders.json) → auch das
# erste Öffnen nach Neustart ist instant. {cat: {"mails":[...], "ts":float}}.
_mail_folders = {}
_mail_folders_lock = threading.Lock()
_mail_folders_refreshing = set()
_MAIL_FOLDERS_FILE = os.path.join(_DATA_DIR, "mail_folders.json")


def _mail_folders_load():
    try:
        with open(_MAIL_FOLDERS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for cat, ent in d.items():
                if isinstance(ent, dict) and isinstance(ent.get("mails"), list):
                    _mail_folders[cat] = {"mails": ent["mails"],
                                          "ts": float(ent.get("ts") or 0.0)}
    except Exception:
        pass


def _mail_folders_save():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _mail_folders_lock:
            snap = {c: {"mails": e["mails"], "ts": e["ts"]}
                    for c, e in _mail_folders.items()}
        tmp = _MAIL_FOLDERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, _MAIL_FOLDERS_FILE)
    except Exception as e:
        state.push_log(f"MAIL: Ordner-Cache speichern — {type(e).__name__}: {e}")


_mail_folders_load()


def _folder_fetch_store(cat):
    """Ordner-Inhalt LIVE holen und in Cache + auf Disk ablegen; gibt die
    Mail-Liste zurück."""
    mails = mail.folder_mails(cat, limit=200)
    with _mail_folders_lock:
        _mail_folders[cat] = {"mails": mails, "ts": time.time()}
    _mail_folders_save()
    return mails


def _folder_refresh_async(cat):
    """Ordner im Hintergrund auffrischen (dedup je Kategorie). True, wenn ein
    Refresh läuft bzw. gestartet wurde."""
    with _mail_folders_lock:
        if cat in _mail_folders_refreshing:
            return True
        _mail_folders_refreshing.add(cat)

    def _run():
        try:
            _folder_fetch_store(cat)
        except Exception as e:
            state.push_log(f"MAIL: Ordner-Auffrischung ({cat}) — "
                           f"{type(e).__name__}: {e}")
        finally:
            with _mail_folders_lock:
                _mail_folders_refreshing.discard(cat)

    threading.Thread(target=_run, daemon=True, name="mail-folder").start()
    return True


def _folder_cache_remove_uid(cat, uid):
    """Eine gelöschte Mail SOFORT aus dem Cache nehmen, damit sie beim nächsten
    (gecachten) Öffnen nicht wieder auftaucht."""
    with _mail_folders_lock:
        ent = _mail_folders.get(cat)
        if ent:
            ent["mails"] = [m for m in ent["mails"] if m.get("uid") != uid]
        else:
            return
    _mail_folders_save()


@bp.route('/api/mail')
def api_mail():
    """Alles fürs Mail-Panel in einem Rutsch, Drill-down-freundlich:
    `categories` = Ebene 1 (alle Kategorien zum Auswählen). `count` ist der
    lokale Schnappschuss; `live_counts` (separat) trägt die ECHTE Ordnergröße
    aus dem Cache, sobald aufgefrischt. `can_poll` = Passphrase vorhanden,
    `polling`/`counts_refreshing` = Hintergrund-Aktivität läuft."""
    try:
        return jsonify({
            "categories": mail.category_overview(),
            "recent": mail.recent(limit=200),
            "live_counts": _mail_live["counts"],
            "counts_age_s": (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None,
            "counts_refreshing": _mail_live["refreshing"],
            "can_poll": mail_secrets.available(),
            "polling": _mail_poll_running["on"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/refresh-counts', methods=['POST'])
def api_mail_refresh_counts():
    """Frischt den LIVE-Ordnerzähl-Cache im Hintergrund auf (IMAP STATUS-Sweep).
    Kehrt sofort zurück; das Ergebnis erscheint beim nächsten /api/mail. Key-
    gegatet, Parallel-Refresh verhindert."""
    if not mail_secrets.available():
        return jsonify({"ok": False, "error": "kein key"}), 409
    # Frische Zahlen nicht unnötig neu sweepen: ein STATUS-Sweep über alle
    # Kategorie-Ordner belegt die (eine) gepoolte Verbindung und lässt einen
    # gleichzeitigen Ordner-Aufruf warten. Innerhalb der TTL → Cache behalten,
    # außer `?force=1` (bewusstes Auffrischen, z.B. nach Poll/Umsortieren).
    ttl = float(os.environ.get("MAIL_COUNTS_TTL_S", "90"))
    if not request.args.get("force"):
        age = (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None
        if age is not None and age < ttl and _mail_live["counts"]:
            return jsonify({"ok": True, "cached": True, "age_s": age})
    with _mail_live_lock:
        if _mail_live["refreshing"]:
            return jsonify({"ok": True, "already": True})
        _mail_live["refreshing"] = True

    def _run():
        try:
            fresh = mail.folder_counts()
            # Ein gedrosselter/abgebrochener STATUS-Sweep liefert eine LEERE
            # oder LÜCKENHAFTE Zählung (ein Ordner, der Outlook-throttlet, fehlt
            # einfach). Die dürfen die guten persistierten Zahlen NICHT platt-
            # machen — sonst zeigt das Panel nach Neustart wieder den mageren
            # 171er-Schnappschuss und muss neu zählen. Regeln:
            #   • leeres Ergebnis (Totalausfall) → gar nichts überschreiben.
            #   • sonst frisch ÜBER alt mergen: ein Ordner, der diesmal nicht
            #     geantwortet hat, behält seinen letzten echten Wert.
            # Auf gültige Kategorien beschränken, damit gelöschte nicht spuken.
            if fresh:
                valid = {c["name"] for c in mail.category_overview()}
                merged = dict(_mail_live["counts"])
                merged.update(fresh)
                merged = {k: v for k, v in merged.items() if k in valid}
                _mail_live["counts"] = merged
                _mail_live["ts"] = time.time()
                _mail_counts_save()      # echte Zahlen überleben den Neustart
            else:
                state.push_log("MAIL: Ordnerzählung leer (throttle?) — "
                               "behalte alten Zähl-Stand")
        except Exception as e:
            state.push_log(f"MAIL: Ordnerzählung — {type(e).__name__}: {e}")
        finally:
            _mail_live["refreshing"] = False

    threading.Thread(target=_run, daemon=True, name="mail-counts").start()
    return jsonify({"ok": True, "started": True})


@bp.route('/api/mail/folder')
def api_mail_folder():
    """Die Mails EINER Kategorie. Serviert SOFORT aus dem Ordner-Cache (kein
    Warten aufs IMAP) und frischt bei abgelaufenem Cache im Hintergrund auf; nur
    der allererste Aufruf je Kategorie (kalter Cache) holt synchron. `?force=1`
    umgeht den Cache und holt synchron frisch (nach Umsortieren/Löschen). Ohne
    Key oder ohne eigenen Ordner: lokaler Schnappschuss. `cached`/`refreshing`
    sagen, ob die Liste aus dem Cache kam und ob im Hintergrund nachgezogen wird."""
    cat = request.args.get('cat', '')
    if not cat:
        return jsonify({"error": "cat fehlt"}), 400
    force = bool(request.args.get('force'))
    ttl = float(os.environ.get("MAIL_FOLDER_TTL_S", "120"))
    try:
        if not mail_secrets.available():
            mails = mail.in_category(cat, limit=200)
            return jsonify({"cat": cat, "mails": mails, "live": False,
                            "source": "snapshot"})
        if force:                       # bewusst frisch (nach Mutation)
            mails = _folder_fetch_store(cat)
            return jsonify({"cat": cat, "mails": mails, "live": True,
                            "source": "live", "cached": False, "refreshing": False})
        with _mail_folders_lock:
            ent = _mail_folders.get(cat)
            ent = {"mails": ent["mails"], "ts": ent["ts"]} if ent else None
        if ent is not None:             # instant aus Cache, ggf. Hintergrund-Refresh
            age = time.time() - ent["ts"]
            refreshing = _folder_refresh_async(cat) if age >= ttl else False
            return jsonify({"cat": cat, "mails": ent["mails"], "live": True,
                            "source": "cache", "cached": True,
                            "age_s": age, "refreshing": refreshing})
        mails = _folder_fetch_store(cat)   # kalt: einmal synchron, dann gecacht
        return jsonify({"cat": cat, "mails": mails, "live": True,
                        "source": "live", "cached": False, "refreshing": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/body')
def api_mail_body():
    """Voller Text + Header EINER Mail (Lesemodus). LIVE aus dem Ordner; braucht
    Key. Query: `cat`, `uid`, optional `account`, optional `prefetch` (Komma-
    Liste von Nachbar-uids → werden im Hintergrund in den Body-Cache geholt,
    damit n/N im Panel instant ist)."""
    cat = request.args.get('cat', '')
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        body = mail.mail_body(cat, uid, account_name=account)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    # Nachbarn vorwärmen (best-effort, nie blockierend) — die nächste/vorige
    # Mail liegt dann schon im Cache, wenn der Nutzer weiterblättert.
    pf = request.args.get('prefetch', '')
    neigh = [int(x) for x in pf.split(',') if x.strip().lstrip('-').isdigit()]
    if neigh:
        threading.Thread(
            target=lambda: mail.prefetch_bodies(cat, neigh, account_name=account),
            daemon=True, name="mail-prefetch").start()
    return jsonify(body)


@bp.route('/api/mail/assign', methods=['POST'])
def api_mail_assign():
    """Den ABSENDER einer Kategorie zuordnen (Keymap) UND **alle** seine
    vorhandenen Mails (alt + neu) in den Kategorie-Ordner verschieben — Sashas
    Modell: pro Absender EINE Kategorie. Mit Key: live umsortiert (`moved` zählt);
    ohne Key: nur Keymap (künftige Mails). Body: `{sender, category}`."""
    body = request.get_json(silent=True) or {}
    sender = (body.get('sender') or '').strip()
    category = (body.get('category') or '').strip()
    if not sender or not category:
        return jsonify({"error": "sender/category fehlt"}), 400
    try:
        res = mail.refile_sender(sender, category)
        # Der Umzug ist jetzt keymap-getrieben und kann aus MEHREREN Ordnern
        # gezogen haben (INBOX + jeder move-Ordner). Statt einzelne Herkünfte zu
        # raten den ganzen Ordner-Cache verwerfen — das nächste Öffnen holt frisch.
        with _mail_folders_lock:
            _mail_folders.clear()
        _mail_folders_save()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/delete', methods=['POST'])
def api_mail_delete():
    """Eine Mail in den Papierkorb verschieben (umkehrbar). LIVE; braucht Key.
    Body: `{cat, uid, account?}`."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — löschen nur live"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    account = body.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    try:
        ok = mail.delete_mail(cat, int(uid), account_name=account)
        if ok:                          # gelöschte Mail sofort aus dem Cache nehmen
            _folder_cache_remove_uid(cat, int(uid))
        return jsonify({"ok": bool(ok)}), (200 if ok else 502)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/reply', methods=['POST'])
def api_mail_reply():
    """Antwort auf eine Mail. LIVE; braucht Key. Body: `{cat, uid, text,
    account?, draft?}`. To/Betreff/Threading leitet das Backend aus der
    Original-Mail ab. `draft:true` → speichert die Antwort als ENTWURF im
    Drafts-Ordner (IMAP APPEND) statt sie per SMTP zu senden."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — senden nicht möglich"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    text = body.get('text') or ''
    account = body.get('account') or None
    draft = bool(body.get('draft'))
    if not cat or uid is None or not text.strip():
        return jsonify({"error": "cat/uid/text fehlt"}), 400
    if draft:
        res = mail.draft_reply(cat, int(uid), text, account_name=account)
    else:
        res = mail.reply_to_mail(cat, int(uid), text, account_name=account)
    if res.get("error"):
        return jsonify(res), 502
    return jsonify(res)


@bp.route('/api/mail/poll', methods=['POST'])
def api_mail_poll():
    """Stößt einen LIVE-Poll im Hintergrund an (explizite Nutzer-Aktion =
    Einwilligung; Move/Trash sind umkehrbar). Kehrt sofort zurück — der
    Fortschritt läuft über die normalen Log-Streams. Verhindert Parallel-Polls."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Live-Poll möglich"}), 409
    with _mail_poll_lock:
        if _mail_poll_running["on"]:
            return jsonify({"ok": True, "already": True})
        _mail_poll_running["on"] = True

    def _run():
        try:
            mail.poll_all(dry_run=False)
            # Der Poll hat Mails in ihre Ordner geräumt → alle Ordner-Caches sind
            # veraltet. Komplett verwerfen; das nächste Öffnen holt frisch.
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Poll abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_poll_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-poll").start()
    return jsonify({"ok": True, "started": True})


@bp.route('/api/mail/reconcile', methods=['POST'])
def api_mail_reconcile():
    """Gleicht die Server-Ordner an die Keymap an (bereits einsortierte Mail
    nachziehen) — im Hintergrund-Thread, kehrt SOFORT zurück, blockiert die GUI
    also nie. Explizite Nutzer-Aktion = Einwilligung (Move/Trash umkehrbar). Key-
    gegatet, Parallel-Reconcile via Lock verhindert. Fortschritt läuft über die
    Log-Streams; das Panel bleibt bedienbar."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Abgleich möglich"}), 409
    with _mail_reconcile_lock:
        if _mail_reconcile_running["on"]:
            return jsonify({"ok": True, "already": True})
        _mail_reconcile_running["on"] = True

    def _run():
        try:
            mail.reconcile_all(dry_run=False)
            # Mails wurden umgeräumt → alle Ordner-Caches sind veraltet.
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Reconcile abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_reconcile_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-reconcile").start()
    return jsonify({"ok": True, "started": True})


@bp.route('/api/mail/inbox')
def api_mail_inbox():
    """Der Eingang-Tray: die INBOX mit Gelesen-Flag (`\\Seen`) + vermuteter
    Kategorie je Mail. LIVE; braucht Key (ohne → leer). Neue/ungelesene Mail liegt
    hier, bis Sasha sie liest — dann sortiert sie sich (bekannter Absender) ein."""
    if not mail_secrets.available():
        return jsonify({"mails": [], "live": False, "source": "kein key"})
    try:
        return jsonify({"mails": mail.inbox_tray(limit=200), "live": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/inbox-body')
def api_mail_inbox_body():
    """Voller Text EINER Eingang-Mail (INBOX). LIVE; braucht Key. Query: `uid`,
    optional `account`. Read-only (PEEK) → hakt die Mail NICHT ab."""
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        return jsonify(mail.inbox_body(uid, account_name=account))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/mail/read', methods=['POST'])
def api_mail_read():
    """Eine Eingang-Mail abhaken: als gelesen markieren (`\\Seen`) und, wenn der
    Absender bekannt ist, sofort einsortieren. LIVE; braucht Key. Body:
    `{uid, account?}`. Sortiert sie ein → alle Ordner-Caches verwerfen."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — abhaken nur live"}), 409
    body = request.get_json(silent=True) or {}
    uid = body.get('uid')
    account = body.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    try:
        res = mail.mark_seen_and_file(int(uid), account_name=account)
        if res.get("filed"):        # Mail wanderte in einen Ordner → Caches stale
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
