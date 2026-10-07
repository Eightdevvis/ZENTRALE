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
#     Ausnahme: eine Anfrage, die sich zu lange nicht regt, gilt als hängend
#     und zählt nicht mehr (STILL_GRENZE_S, seit 2026-10-07).
#     Die Debug-Streams fürs Devtool hängen dauerhaft und zählen nicht.
#
# Abschalten: ZENTRALE_HOT_RELOAD=aus. /reboot bleibt für den harten Fall.

import os
import sys
import threading
import time

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ORDNER = ('core', 'ui', 'tutor')

# Dauer-Streams, die nie enden — würden den Reload ewig blockieren.
_IGNORIERT = ('/api/ai/debug/stream', '/api/tutor/debug/stream')

_laufend_lock = threading.Lock()


def an() -> bool:
    raw = (os.environ.get("ZENTRALE_HOT_RELOAD") or "").strip().lower()
    return raw not in ("aus", "0", "off", "false")


def code_dateien(root=_ROOT, ordner=ORDNER):
    """Alle *.py unter den Backend-Ordnern, ohne Tests und __pycache__."""
    out = []
    for o in ordner:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, o)):
            # skill_vorlagen: fremder Beispielcode der Skills (Anthropic), den
            # das Backend nie importiert — eine Änderung dort ist kein Grund
            # für einen Neustart (2026-10-07).
            dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'skill_vorlagen')]
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
#
# 2026-10-07: Bis heute zählten before_request (rein) und after_request →
# response.call_on_close (raus). Das hat Löcher, in denen ein Request für
# immer als laufend galt und der Hot Reload nie mehr kam (Journal ab 23:26:
# „wartet: 1 laufende(r) Request(s)", bis zum Neustart von Hand):
#   - Antworten mit direct_passthrough (send_file/send_from_directory, also
#     auch /static) gibt werkzeug ohne ClosingIterator heraus — call_on_close
#     feuert nie,
#   - eine Ausnahme in einem after_request, das vor unserem läuft, oder in
#     einem teardown — dann läuft unser after_request bzw. das close nie,
#   - der Dev-Server ruft close erst NACH seinem Leselauf auf dem Socket
#     (werkzeug/serving.py, execute: finally); hängt der, hängt der Zähler.
# Welcher Weg es am 07.10. war, war nicht mehr festzustellen (Backend da
# schon von Hand neu gestartet) — deshalb nennt die Meldung jetzt den Pfad.
# Deshalb jetzt eine Schicht AUSSEN um die WSGI-App: rein beim Betreten,
# raus genau einmal — wenn die Antwort fertig durchgelaufen ist, wenn sie
# mit einer Ausnahme abbricht oder wenn der Server sie schließt, was zuerst
# kommt. Flask und werkzeug-Interna können nichts mehr dazwischenschieben.
#
# Pro Anfrage gemerkt: Pfad, Beginn, letzte Regung (letztes Stück Antwort).
# Damit sagt das Log, WER blockiert, und eine Anfrage, die sich ewig nicht
# mehr regt, hält den Neustart nicht mehr auf (siehe still_grenze).

# Ab so viel Stille gilt eine Anfrage als hängend und blockiert den Neustart
# nicht mehr. 10 min: Nichts, was die TUI sonst abfragt, braucht auch nur
# eine Minute; ein Chat-Strom regt sich bei jedem Token und jedem Werkzeug-
# Schritt, die längste vorgesehene Pause darin ist die Erlaubnis-Frage
# (state.wait_permission, 180 s).
STILL_GRENZE_S = 10 * 60
# Ausnahme Chat: run_code darf mit Erlaubnis bis 30 min laufen
# (sandbox.ZEITLIMIT_MAX_S) und der Strom ist währenddessen still. Ein
# Neustart mittendrin schnitte die Antwort ab — also für die Chat-Ströme die
# Grenze darüber. Ein Test hält beide Zahlen zusammen.
STILL_GRENZE_CHAT_S = 35 * 60
_CHAT_STROEME = ('/api/chat', '/api/chat/wiederholen')

_anfragen = {}          # nr -> [pfad, beginn, letzte_regung]  (monotonic)
_naechste_nr = 0
_ignoriert_gemeldet = set()


def _jetzt():
    return time.monotonic()


def _rein(pfad, jetzt=None) -> int:
    global _naechste_nr
    t = _jetzt() if jetzt is None else jetzt
    with _laufend_lock:
        _naechste_nr += 1
        _anfragen[_naechste_nr] = [pfad, t, t]
        return _naechste_nr


def _regung(nr):
    with _laufend_lock:
        a = _anfragen.get(nr)
        if a:
            a[2] = _jetzt()


def _raus(nr):
    """Idempotent — zählt genau einmal herunter, egal wie oft gerufen."""
    with _laufend_lock:
        _anfragen.pop(nr, None)
        _ignoriert_gemeldet.discard(nr)


def laufende_requests() -> int:
    with _laufend_lock:
        return len(_anfragen)


def still_grenze(pfad) -> int:
    return STILL_GRENZE_CHAT_S if pfad in _CHAT_STROEME else STILL_GRENZE_S


class _Antwort:
    """Umhüllt das Antwort-Iterable: jedes Stück ist eine Regung, das Ende
    (fertig, Ausnahme oder close) zählt herunter."""

    def __init__(self, inneres, nr):
        self._inneres = inneres
        self._iter = None
        self._nr = nr

    def __iter__(self):
        self._iter = iter(self._inneres)
        return self

    def __next__(self):
        try:
            stueck = next(self._iter)
        except BaseException:           # StopIteration = fertig, sonst Abbruch
            _raus(self._nr)
            raise
        _regung(self._nr)
        return stueck

    def close(self):
        try:
            schliessen = getattr(self._inneres, 'close', None)
            if schliessen:
                schliessen()
        finally:
            _raus(self._nr)


class _Zaehler:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        pfad = environ.get('PATH_INFO') or ''
        if pfad in _IGNORIERT:
            return self.wsgi_app(environ, start_response)
        nr = _rein(pfad)
        try:
            inneres = self.wsgi_app(environ, start_response)
        except BaseException:
            _raus(nr)
            raise
        return _Antwort(inneres, nr)


def requests_zaehlen(app):
    """Hängt den Zähler an die Flask-App. Ein Request gilt als laufend, bis
    seine Antwort ganz durch ist — bei einem SSE-Stream also bis zum letzten
    Token, nicht nur bis die Kopfzeilen raus sind."""
    app.wsgi_app = _Zaehler(app.wsgi_app)


def _dauer(s) -> str:
    return "unter 1 min" if s < 60 else f"{int(s // 60)} min"


def beschaeftigt(log=None, jetzt=None) -> str | None:
    """Warum JETZT kein Neustart geht — oder None. Nennt die laufenden
    Anfragen mit Pfad und Alter; hängende (zu lange still) zählen nicht und
    werden einmal ins Log geschrieben."""
    t = _jetzt() if jetzt is None else jetzt
    with _laufend_lock:
        alle = [(nr, *a) for nr, a in _anfragen.items()]
    aktiv = []
    for nr, pfad, beginn, regung in sorted(alle, key=lambda x: x[2]):
        if t - regung >= still_grenze(pfad):
            if log and nr not in _ignoriert_gemeldet:
                log(f"HOT RELOAD ignoriere hängende Anfrage {pfad} "
                    f"(seit {_dauer(t - beginn)}, {_dauer(t - regung)} still)")
                _ignoriert_gemeldet.add(nr)
            continue
        aktiv.append(f"{pfad} seit {_dauer(t - beginn)}")
    if aktiv:
        return ", ".join(aktiv)
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

    def tick(self, grund_jetzt=None) -> bool:
        """True = jetzt neu starten. grund_jetzt: ersetzt beschaeftigt() (Tests)."""
        self.tick_nr += 1
        if self.tick_nr % self.alle:
            return False
        neu = code_stand(self.dateien())
        if neu == self.alt:
            return False
        if neu != self.kandidat:            # Code bewegt sich noch
            self.kandidat = neu
            return False
        grund = grund_jetzt() if grund_jetzt else beschaeftigt(self.log)
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
