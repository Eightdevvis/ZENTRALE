# core/app_verwaltung.py
#
# Der Hub verwaltet seine Prozess-Apps (Hub-Grundlagen, 2026-10-22,
# memory/hub/hub_bauplan.md „Apps starten, stoppen, weiterreichen"):
#
#   liste()          GET /api/apps — alle installierten Apps aus ihren
#                    Manifesten, bei Prozess-Apps mit `laeuft`
#   starten(name)    POST /api/apps/<name>/start — läuft sie schon (egal, wer
#                    sie gestartet hat), passiert nichts
#   stoppen(name)    POST /api/apps/<name>/stop — NUR, was der Hub selbst
#                    gestartet hat; eine fremd gestartete App (systemd am PC,
#                    Sasha im Terminal, das Zimmer) bleibt unangetastet
#   autostart()      beim Start des Backends: jede App mit `autostart = true`
#   eigene_stoppen() beim Ende des Backends
#
# Wer „eigen" ist, steht nicht nur im Speicher: der Hot Reload ersetzt den
# Backend-Prozess per exec (core/hot_reload.py), die Apps laufen weiter. Darum
# legt der Hub je gestarteter App eine Marke ab (<lauf_ordner>/<name>.pid:
# Prozessnummer + Startzeit laut /proc) und erkennt sie nach dem exec wieder.
# Passt die Startzeit nicht (Nummer neu vergeben), ist die Marke wertlos.
#
# Die Handgriffe selbst (Python der App, Befehl, /hub/gesund, anhalten) teilt
# der Hub mit dem Zimmer-Starter: core/app_prozess.py.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import ai_config
import app_prozess
import apps
import state

GESUND_WARTEZEIT = 0.4       # /api/apps fragt alle Apps parallel, kurz
START_WARTEZEIT = 15.0       # so lange darf eine App zum Hochfahren brauchen

_lock = threading.Lock()
_eigene = {}                 # name → (proc|None, logf|None, pid)


def _log(text):
    print("[apps] " + text, flush=True)
    try:
        state.push_log("APPS  " + text)
    except Exception:
        pass


# ── Marken: was der Hub gestartet hat ─────────────────────────────────

def lauf_ordner() -> str:
    """Wo die Marken liegen (Einstellung app_lauf_ordner; Standard im
    Laufzeit-Ordner des Nutzers — nach einem Neustart des Rechners leer)."""
    eigen = ai_config.setting("app_lauf_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    basis = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(basis, "zentrale-apps-%d" % os.getuid())


def _marke(name):
    return os.path.join(lauf_ordner(), name + ".pid")


def _startzeit(pid):
    """Startzeit des Prozesses laut /proc (Feld 22), None wenn er nicht lebt."""
    try:
        with open("/proc/%d/stat" % pid, encoding="ascii") as f:
            return f.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def _marke_schreiben(name, pid):
    os.makedirs(lauf_ordner(), exist_ok=True)
    tmp = _marke(name) + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        f.write("%d %s\n" % (pid, _startzeit(pid) or "?"))
    os.replace(tmp, _marke(name))


def _marke_lesen(name):
    """Prozessnummer aus der Marke, wenn sie noch zum lebenden Prozess passt."""
    try:
        with open(_marke(name), encoding="ascii") as f:
            pid_text, zeit = f.read().split()
        pid = int(pid_text)
    except (OSError, ValueError):
        return None
    if zeit != "?" and _startzeit(pid) == zeit:
        return pid
    _marke_loeschen(name)
    return None


def _marke_loeschen(name):
    try:
        os.remove(_marke(name))
    except OSError:
        pass


def gestartet_vom_hub(name) -> bool:
    """Hat der Hub diese App gestartet, und lebt sie noch?"""
    with _lock:
        e = _eigene.get(name)
    if e is not None:
        proc, _logf, pid = e
        if (proc.poll() is None) if proc is not None else (_startzeit(pid) is not None):
            return True
        with _lock:
            _eigene.pop(name, None)
        _marke_loeschen(name)
        return False
    pid = _marke_lesen(name)                     # nach einem Hot Reload
    if pid is not None:
        with _lock:
            _eigene.setdefault(name, (None, None, pid))
        return True
    return False


# ── Liste ─────────────────────────────────────────────────────────────

def _eintrag(m, laeuft):
    name = str(m.get("_slug") or m.get("name") or "")
    prozess = apps.ist_prozess(m)
    return {
        "name": name,
        "titel": str(m.get("titel") or m.get("name") or name),
        "version": str(m.get("version") or ""),
        "art": "prozess" if prozess else "vorlage",
        "adresse": str(m["adresse"]) if prozess else None,
        "laeuft": laeuft if prozess else None,
        "gestartet_vom_hub": gestartet_vom_hub(name) if prozess else False,
        "autostart": bool(m.get("autostart")) if prozess else False,
        "ansichten": [str(a) for a in (m.get("ansichten") or [])],
        "rechte": [str(r) for r in (m.get("rechte") or [])],
        "liefert": [str(x) for x in (m.get("liefert") or [])],
        "routen": apps.routen(m),
        "daten": apps.daten(m),
        # seit 2026-10-25 (Apps aus dem Schaufenster): woher sie kommt, was
        # auf diesem Rechner eingerichtet ist, ihr Symbol fürs Rad
        "quelle": (m.get("_installiert") or {}).get("quelle"),
        "ansichten_installiert": apps.ansichten_installiert(m),
        "icon": apps.icon(m["_pfad"], m),
    }


def liste() -> list:
    """Alle installierten Apps (GET /api/apps). Prozess-Apps werden parallel
    gefragt, ob sie leben (je höchstens GESUND_WARTEZEIT)."""
    alle = apps.installiert()
    prozess = [m for m in alle if apps.ist_prozess(m)]
    lebt = {}
    if prozess:
        with ThreadPoolExecutor(max_workers=min(8, len(prozess))) as pool:
            for m, ja in zip(prozess, pool.map(
                    lambda m: app_prozess.lebt(m["adresse"], GESUND_WARTEZEIT), prozess)):
                lebt[id(m)] = ja
    return [_eintrag(m, lebt.get(id(m))) for m in alle]


# ── Starten / Stoppen ────────────────────────────────────────────────

class AppFehler(Exception):
    """status + antwort für die Route."""

    def __init__(self, status, antwort):
        super().__init__(antwort.get("text") or antwort.get("fehler"))
        self.status, self.antwort = status, antwort


def _log_pfad(name):
    return os.path.join(tempfile.gettempdir(), "zentrale-app-%s.log" % name)


_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def _manifest(name):
    """Manifest einer App mit gültigem Namen, sonst AppFehler 404."""
    m = apps.manifest(name) if _NAME.fullmatch(str(name)) else None
    if m is None:
        raise AppFehler(404, {"fehler": "unbekannt", "text": "app „%s\" ist nicht installiert" % name})
    return m


def starten(name: str) -> dict:
    """App starten, falls sie nicht schon lebt. → {name, laeuft, gestartet}
    (gestartet = von diesem Aufruf). Wirft AppFehler."""
    m = _manifest(name)
    if not apps.ist_prozess(m):
        raise AppFehler(400, {"fehler": "kein_prozess",
                              "text": "„%s\" ist keine prozess-app (kein start/adresse)" % name})
    if app_prozess.lebt(m["adresse"]):
        return {"name": name, "laeuft": True, "gestartet": False}
    with _lock:
        alt = _eigene.get(name)
        if alt is not None and alt[0] is not None and alt[0].poll() is None:
            # schon gestartet, aber noch nicht gesund: nicht doppelt starten
            return {"name": name, "laeuft": False, "gestartet": False}
    kommando = apps.befehl(m, m["start"])
    try:
        proc, logf = app_prozess.starten(m["_pfad"], kommando, _log_pfad(name),
                                         adresse=m["adresse"], warten_s=START_WARTEZEIT)
    except OSError as e:
        raise AppFehler(503, {"fehler": "aus", "text": "„%s\" startet nicht: %s" % (name, e)})
    if proc.poll() is not None:
        logf.close()
        raise AppFehler(503, {"fehler": "aus", "text": "„%s\" ist beim start gleich wieder "
                                                       "ausgegangen (log: %s)" % (name, _log_pfad(name))})
    with _lock:
        _eigene[name] = (proc, logf, proc.pid)
    try:
        _marke_schreiben(name, proc.pid)
    except OSError as e:
        _log("marke für %s nicht geschrieben: %s" % (name, e))
    laeuft = app_prozess.lebt(m["adresse"])
    _log("%s gestartet (pid %d)%s" % (name, proc.pid, "" if laeuft else " — noch nicht gesund"))
    return {"name": name, "laeuft": laeuft, "gestartet": True}


def stoppen(name: str) -> dict:
    """Nur stoppen, was der Hub gestartet hat. → {name, gestoppt}."""
    _manifest(name)
    if not gestartet_vom_hub(name):
        raise AppFehler(409, {"fehler": "fremd",
                              "text": "„%s\" hat der hub nicht gestartet — er lässt sie in ruhe" % name})
    with _lock:
        proc, logf, pid = _eigene.pop(name)
    if proc is not None:
        app_prozess.anhalten(proc, logf)
    else:                                         # nach einem Hot Reload: nur die Nummer
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _marke_loeschen(name)
    _log("%s gestoppt" % name)
    return {"name": name, "gestoppt": True}


def autostart_an() -> bool:
    """Einstellung apps_autostart (Standard an; „aus" z. B. am Laptop mit
    wenig RAM)."""
    return str(ai_config.setting("apps_autostart", "an")).lower() not in ("aus", "0", "off", "false", "nein")


def autostart() -> list:
    """Jede installierte Prozess-App mit `autostart = true` starten (falls
    sie nicht schon läuft). Fehler werden geloggt, nie geworfen — das Backend
    läuft auch ohne seine Apps. → Namen der gestarteten Apps."""
    if not autostart_an():
        _log("autostart aus (einstellung apps_autostart)")
        return []
    raus = []
    for m in apps.installiert():
        if not (apps.ist_prozess(m) and m.get("autostart")):
            continue
        name = str(m.get("name") or "")
        try:
            if starten(name)["gestartet"]:
                raus.append(name)
        except AppFehler as e:
            _log("autostart %s: %s" % (name, e))
        except Exception as e:                    # nie das Backend reißen
            _log("autostart %s: unerwartet: %s" % (name, e))
    return raus


def eigene_stoppen() -> list:
    """Alles stoppen, was der Hub gestartet hat (Ende des Backends)."""
    with _lock:
        namen = list(_eigene)
    raus = []
    for name in namen:
        try:
            stoppen(name)
            raus.append(name)
        except Exception as e:
            _log("stoppen %s: %s" % (name, e))
    return raus
