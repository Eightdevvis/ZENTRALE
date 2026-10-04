# core/hot_reload.py
#
# Hot Reload fürs Backend — Gegenstück zum Hot Reload der TUI
# (tui/zentrale_tui.py, RELOAD).
#
# Sasha, 04.10.2026: „hot reload soll auch backend neu laden". Das Backend
# beobachtet seine eigenen Quellen (core/, ui/, tutor/ — nur *.py, ohne
# test_*.py); ändern sie sich (Merge nach main, Edit), ersetzt sich der
# Prozess per exec durch sich selbst: gleiche pid (systemd merkt nichts),
# frischer Code, nach ein, zwei Sekunden antwortet :5000 wieder.
#
# Bewusst KEIN importlib.reload: Module im laufenden Prozess tauschen geht
# bei Threads, Flask-Routen und globalem Zustand schief. Ein ganzer Neustart
# ist ehrlich und kostet nur den Zustand, den /reboot auch kostet.
#
# Wie bei der TUI:
#   - erst wenn der Code eine Prüfung lang ruht (ein Merge schreibt mehrere
#     Dateien nacheinander),
#   - nur wenn er kompiliert — sonst bleibt der alte laufen, laut im Log,
#     und erst die nächste Änderung zählt,
#   - nie mitten in etwas: kein laufender Request (ein Chat-Stream samt
#     Erlaubnis-Frage ist ein laufender Request), keine aktive Tutor-Session.
#     Die Debug-Streams fürs Devtool hängen dauerhaft und zählen nicht.
#
# Abschalten: ZENTRALE_HOT_RELOAD=aus. /reboot bleibt für den harten Fall.

import os
import sys
import threading

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ORDNER = ('core', 'ui', 'tutor')

# Dauer-Streams, die nie enden — würden den Reload ewig blockieren.
_IGNORIERT = ('/api/ai/debug/stream', '/api/tutor/debug/stream')

_laufend = 0
_laufend_lock = threading.Lock()


def an() -> bool:
    raw = (os.environ.get("ZENTRALE_HOT_RELOAD") or "").strip().lower()
    return raw not in ("aus", "0", "off", "false")


def code_dateien(root=_ROOT, ordner=ORDNER):
    """Alle *.py unter den Backend-Ordnern, ohne Tests und __pycache__."""
    out = []
    for o in ordner:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, o)):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for n in filenames:
                if n.endswith('.py') and not n.startswith('test_'):
                    out.append(os.path.join(dirpath, n))
    return sorted(out)


def code_stand(dateien):
    """Fingerabdruck des Codes: (pfad, mtime_ns, größe) je Datei."""
    stand = []
    for p in dateien:
        try:
            st = os.stat(p)
            stand.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            stand.append((p, None, None))
    return tuple(stand)


def code_fehler(dateien):
    """Erste Datei, die nicht kompiliert, als kurze Meldung — sonst None."""
    for p in dateien:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                compile(f.read(), p, 'exec')
        except (SyntaxError, ValueError, UnicodeDecodeError) as e:
            zeile = getattr(e, 'lineno', None)
            ort = os.path.relpath(p, _ROOT) + (f":{zeile}" if zeile else "")
            return f"{ort} {type(e).__name__}"
        except OSError:
            continue        # gerade gelöscht/umbenannt — nächste Runde zählt
    return None


# ── Laufende Requests zählen ────────────────────────────────────────────

def _rein():
    global _laufend
    with _laufend_lock:
        _laufend += 1


def _raus():
    global _laufend
    with _laufend_lock:
        _laufend = max(0, _laufend - 1)


def laufende_requests() -> int:
    with _laufend_lock:
        return _laufend


def requests_zaehlen(app):
    """Hängt den Zähler an die Flask-App. Ein Request gilt bis zum Schließen
    seiner Antwort als laufend — bei einem SSE-Stream also bis zum letzten
    Token, nicht nur bis die Kopfzeilen raus sind."""
    from flask import request, g

    @app.before_request
    def _hot_reload_rein():
        if request.path in _IGNORIERT:
            return
        g._hot_reload_gezaehlt = True
        _rein()

    @app.after_request
    def _hot_reload_raus(response):
        if g.pop('_hot_reload_gezaehlt', False):
            response.call_on_close(_raus)
        return response


def beschaeftigt() -> str | None:
    """Warum JETZT kein Neustart geht — oder None."""
    n = laufende_requests()
    if n:
        return f"{n} laufende(r) Request(s)"
    try:
        import tutor_port
        if tutor_port.is_active():
            return "Tutor-Session aktiv"
    except Exception:
        pass
    return None


# ── Der Wächter (von main.py jede Sekunde angestoßen) ──────────────────

class Waechter:
    """Merkt sich den Code-Stand beim Start und entscheidet pro tick(), ob
    neu gestartet wird. Alles Zustandsbehaftete hier drin, damit es testbar
    ist; das exec selbst macht neu_starten()."""

    def __init__(self, log, dateien=code_dateien, alle=2):
        self.log = log
        self.dateien = dateien
        self.alle = alle            # nur jeden n-ten Tick auf die Platte schauen
        self.tick_nr = 0
        self.alt = code_stand(dateien())
        self.kandidat = None
        self.wartet_gemeldet = None

    def tick(self, beschaeftigt=beschaeftigt) -> bool:
        """True = jetzt neu starten."""
        self.tick_nr += 1
        if self.tick_nr % self.alle:
            return False
        neu = code_stand(self.dateien())
        if neu == self.alt:
            return False
        if neu != self.kandidat:            # Code bewegt sich noch
            self.kandidat = neu
            return False
        grund = beschaeftigt()
        if grund:
            if grund != self.wartet_gemeldet:
                self.log(f"HOT RELOAD wartet: {grund}")
                self.wartet_gemeldet = grund
            return False
        fehler = code_fehler(self.dateien())
        if fehler:
            self.log(f"HOT RELOAD verworfen, neuer Code kaputt: {fehler}")
            self.alt = neu                  # erst die nächste Änderung zählt
            self.kandidat = None
            return False
        return True


def neu_starten(log):
    """Prozess durch sich selbst ersetzen.

    Falle: werkzeug macht seinen Lausch-Socket ausdrücklich VERERBBAR
    (serving.py, srv.socket.set_inheritable(True) — für den eigenen
    Reloader). Ohne Gegenmaßnahme überlebt :5000 das exec, und der neue
    Prozess scheitert mit „Address already in use" (im Probelauf gesehen).
    Deshalb vor dem exec alles ab fd 3 schließen."""
    log("HOT RELOAD  neuer Code im Backend — starte neu")
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os.environ.pop("WERKZEUG_SERVER_FD", None)
    try:
        maxfd = os.sysconf("SC_OPEN_MAX")
    except (ValueError, OSError):
        maxfd = 4096
    os.closerange(3, maxfd)
    os.execv(sys.executable, [sys.executable] + sys.argv)
