# core/mail_puffer.py
#
# Die Puffer des Mail-Panels: Live-Ordnerzählung, Ordner-Inhalte und die
# Hintergrund-Jobs (Poll, Abgleich, Zählen, Auffrischen, Vorwärmen).
#
# Schicht 2 (Dienste, memory/system/bauplan_kern.md). Bis 2026-10-06 stand
# all das in den Flask-Routen (ui/app.py, dann ui/routen/mail.py): Zustand,
# Locks, Dateien und Threads in der Schicht, die nur HTTP übersetzen soll.
# Jetzt halten die Routen nur noch Anfrage → Puffer → Antwort, und der
# Puffer ist ohne Flask testbar. Der Code ist unverändert übernommen; nur
# die Stücke, die vorher mitten in einer Route standen, sind benannte
# Funktionen geworden.
#
# Das Panel selbst ist KEY-FREI: Kategorie-Übersicht + Mails lesen nur den
# lokalen Triage-Stand (data/mail_state.json, unverschlüsselt). Die Passphrase
# (Env ODER OS-Keyring) braucht NUR der Live-Poll, der echte IMAP-Aktionen tut.

import json
import os
import threading    # für den Hintergrund-Poll (blockiert den Request nicht)
import time         # für das Alter des Live-Ordnerzähl-Caches

import mail
import state

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

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


def ordner_mail_entfernen(cat, uid):
    """Eine gelöschte Mail SOFORT aus dem Cache nehmen, damit sie beim nächsten
    (gecachten) Öffnen nicht wieder auftaucht."""
    with _mail_folders_lock:
        ent = _mail_folders.get(cat)
        if ent:
            ent["mails"] = [m for m in ent["mails"] if m.get("uid") != uid]
        else:
            return
    _mail_folders_save()


def ordner_verwerfen():
    """Alle Ordner-Caches verwerfen — nach allem, was Mails zwischen Ordnern
    bewegt hat (Umsortieren, Poll, Abgleich, Einsortieren beim Abhaken). Das
    nächste Öffnen holt frisch."""
    with _mail_folders_lock:
        _mail_folders.clear()
    _mail_folders_save()


# ── Was die Routen fragen ──────────────────────────────────────────────

def panel_stand():
    """Die Puffer-Felder für /api/mail: Live-Zahlen, ihr Alter, ob gerade
    gezählt oder gepollt wird."""
    return {
        "live_counts": _mail_live["counts"],
        "counts_age_s": (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None,
        "counts_refreshing": _mail_live["refreshing"],
        "polling": _mail_poll_running["on"],
    }


def zahlen_auffrischen(force):
    """Frischt den LIVE-Ordnerzähl-Cache im Hintergrund auf (IMAP STATUS-Sweep).
    Kehrt sofort zurück; gibt die Antwort für die Route zurück. Der Aufrufer
    prüft vorher, ob ein Key da ist."""
    # Frische Zahlen nicht unnötig neu sweepen: ein STATUS-Sweep über alle
    # Kategorie-Ordner belegt die (eine) gepoolte Verbindung und lässt einen
    # gleichzeitigen Ordner-Aufruf warten. Innerhalb der TTL → Cache behalten,
    # außer `force` (bewusstes Auffrischen, z.B. nach Poll/Umsortieren).
    ttl = float(os.environ.get("MAIL_COUNTS_TTL_S", "90"))
    if not force:
        age = (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None
        if age is not None and age < ttl and _mail_live["counts"]:
            return {"ok": True, "cached": True, "age_s": age}
    with _mail_live_lock:
        if _mail_live["refreshing"]:
            return {"ok": True, "already": True}
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
    return {"ok": True, "started": True}


def ordner(cat, force):
    """Die Mails EINER Kategorie aus dem Puffer (Key vorausgesetzt). Serviert
    SOFORT aus dem Ordner-Cache und frischt bei abgelaufenem Cache im
    Hintergrund auf; nur der allererste Aufruf je Kategorie (kalter Cache)
    holt synchron. `force` umgeht den Cache und holt synchron frisch."""
    ttl = float(os.environ.get("MAIL_FOLDER_TTL_S", "120"))
    if force:                       # bewusst frisch (nach Mutation)
        mails = _folder_fetch_store(cat)
        return {"cat": cat, "mails": mails, "live": True,
                "source": "live", "cached": False, "refreshing": False}
    with _mail_folders_lock:
        ent = _mail_folders.get(cat)
        ent = {"mails": ent["mails"], "ts": ent["ts"]} if ent else None
    if ent is not None:             # instant aus Cache, ggf. Hintergrund-Refresh
        age = time.time() - ent["ts"]
        refreshing = _folder_refresh_async(cat) if age >= ttl else False
        return {"cat": cat, "mails": ent["mails"], "live": True,
                "source": "cache", "cached": True,
                "age_s": age, "refreshing": refreshing}
    mails = _folder_fetch_store(cat)   # kalt: einmal synchron, dann gecacht
    return {"cat": cat, "mails": mails, "live": True,
            "source": "live", "cached": False, "refreshing": False}


def vorwaermen(cat, uids, account):
    """Nachbar-Mails im Hintergrund in den Body-Cache holen (best-effort, nie
    blockierend) — die nächste/vorige Mail liegt dann schon bereit."""
    threading.Thread(
        target=lambda: mail.prefetch_bodies(cat, uids, account_name=account),
        daemon=True, name="mail-prefetch").start()


def poll_starten():
    """Einen LIVE-Poll im Hintergrund anstoßen; verhindert Parallel-Polls."""
    with _mail_poll_lock:
        if _mail_poll_running["on"]:
            return {"ok": True, "already": True}
        _mail_poll_running["on"] = True

    def _run():
        try:
            mail.poll_all(dry_run=False)
            # Der Poll hat Mails in ihre Ordner geräumt → alle Ordner-Caches sind
            # veraltet. Komplett verwerfen; das nächste Öffnen holt frisch.
            ordner_verwerfen()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Poll abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_poll_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-poll").start()
    return {"ok": True, "started": True}


def abgleich_starten():
    """Server-Ordner an die Keymap angleichen, im Hintergrund; verhindert
    Parallel-Abgleiche."""
    with _mail_reconcile_lock:
        if _mail_reconcile_running["on"]:
            return {"ok": True, "already": True}
        _mail_reconcile_running["on"] = True

    def _run():
        try:
            mail.reconcile_all(dry_run=False)
            # Mails wurden umgeräumt → alle Ordner-Caches sind veraltet.
            ordner_verwerfen()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Reconcile abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_reconcile_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-reconcile").start()
    return {"ok": True, "started": True}
