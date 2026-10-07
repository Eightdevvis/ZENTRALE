"""Aufzeichnen-und-Abspielen-Backend für den Bildschirm-Vergleich (lauf.py).

GET: erst im Cache (cache.json) nachsehen; fehlt der Pfad, beim LIVE-Backend
holen (nur lesend!) und merken. Alles andere (POST/PUT/DELETE) beantwortet es
selbst mit {} — kein Tastendruck im Vergleich kann Sashas Daten ändern.
Pfade mit möglichen Nebenwirkungen (Mail-Bodies → \\Seen-Flag) gehen nie live.
"""
import json, os, sys, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIVE = os.environ.get("ZTUI_LIVE", "http://localhost:5000")
CACHE = (os.environ.get("ZTUI_CACHE")
         or os.path.expanduser("~/.cache/zentrale/tui_schirm.json"))  # ECHTE Daten: nie ins Repo
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
NIE_LIVE = ("/api/mail/body", "/api/mail/inbox-body", "/api/mail/poll",
            "/api/mail/reconcile", "/api/mail/refresh-counts", "/api/chat?",
            "/api/tutor/start", "/api/tutor/respond", "/api/tutor/stop")
_lock = threading.Lock()
try:
    with open(CACHE) as f:
        _cache = json.load(f)
except (OSError, ValueError):
    _cache = {}
NUR_CACHE = os.environ.get("ZTUI_NUR_CACHE") == "1"
FEHLT = []


_MAILS = {"mails": [
    {"uid": 11, "from": "Anna Beispiel <anna@example.org>", "subject": "Treffen am Freitag",
     "seen": False, "account": "a", "category": "arbeit"},
    {"uid": 12, "from": "Bank <info@bank.example>", "subject": "Kontoauszug",
     "seen": True, "account": "a"},
    {"uid": 13, "from": "Verein", "subject": "", "seen": False, "account": "b"}],
    "live": False}
_BODY = {"body": "Hallo,\n\nwie besprochen treffen wir uns am Freitag um 18 Uhr am "
         "Bahnhof. Bring bitte die Unterlagen mit, und denk an den Schluessel fuer "
         "den Keller.\n\n" + "Eine lange Zeile ohne Umbruch " * 12 + "\n\nGruss\nAnna"}


_EINSTELLUNGEN = {
    "anbieter": "auto", "anbieter_aktiv": "claude", "modell": "claude-sonnet-5",
    "effort": "low", "effort_stufen": ["low", "medium", "high", "xhigh", "max"],
    "effort_wirkt": True, "budget": 20.0, "weg": "cloud",
    "budget_lage": {"status": "ok", "ausgegeben": 3.12, "limit": 20.0, "anteil": 0.156},
    "anbieter_liste": [
        {"name": "claude", "schluessel": True, "spricht": True, "modell": "claude-sonnet-5",
         "modelle": ["claude-sonnet-5", "claude-haiku-4-5"]},
        {"name": "qwen", "schluessel": True, "spricht": True, "modell": "qwen-plus",
         # Seit 2026-10-07 die ganze Liste des Anbieters (Blättern/Filtern).
         "modelle": ["qwen-plus", "qwen-turbo"] + ["qwen3-%d-instruct" % i for i in range(40)]}]}

# /erlaubnis (2026-10-07): was ohne Frage erlaubt ist.
_ERLAUBNIS = {"immer": [{"name": "run_code", "was": "programme abgeschottet ausführen"}],
              "gespraech": [{"name": "web_search", "was": "im internet suchen"}],
              "gespraech_id": "g1"}


# Erfundene Gespräche (Claude-Web-Plan Phase 2, 2026-10-07): Liste mit
# Erinnerungen oben, ein offenes Gespräch mit Denken und Werkzeug.
_GESPRAECHE = {"aktiv": "g1", "gespraeche": [
    {"id": "erinnerungen", "titel": "Erinnerungen", "letzte": "2026-10-06T09:55:00+00:00",
     "anzahl": 2, "ungelesen": True},
    {"id": "g1", "titel": "Fahrradschlauch flicken unterwegs",
     "letzte": "2026-10-06T08:00:00+00:00", "anzahl": 2},
    {"id": "g2", "titel": "Steuererklärung Belege sortieren",
     "letzte": "2026-10-03T08:00:00+00:00", "anzahl": 6}]}
_ARCHIV = {"aktiv": "g1", "gespraeche": [
    {"id": "g0", "titel": "Alter Umzugsplan", "letzte": "2026-08-01T08:00:00+00:00",
     "anzahl": 4, "archiviert": True}]}
_VERLAUF = [
    {"id": "n1", "role": "user", "content": "wie flicke ich unterwegs einen schlauch?"},
    {"id": "n2", "role": "assistant", "content": "Mit Flickzeug: Loch suchen, anrauen, "
     "Kleber, warten, Flicken drauf.",
     "denken": "Er fragt nach unterwegs — also ohne Wasserbad. " * 6,
     "werkzeuge": [{"name": "read_note", "args": "name=fahrrad",
                    "ergebnis": "Flickzeug liegt in der Satteltasche."},
                   {"name": "web_search", "args": "query=schlauch flicken", "fehler": True,
                    "ergebnis": "kein netz"}],
     "dokumente": [{"id": "d1", "titel": "Packliste Radtour"}]}]


# Erfundenes Gedächtnis (Claude-Web-Plan Phase 3, 2026-10-07): die echten
# Kernakten sind persönlich und gehen nie in den Cache.
_GEDAECHTNIS = {
    "kernakten": [
        {"akte": "hausregeln", "stand": "a1", "text": "# Hausregeln\n\n- Nicht duzen "
         "lassen, sondern selbst duzen.  _(seit 01.10.2026)_\n- Kurz antworten, "
         "ausser ich frage nach Details.  _(seit 03.10.2026)_\n"},
        {"akte": "steckbrief", "stand": "b2", "text": "# Sasha\n\n## Alltag\n"
         + "Studiert, faehrt Rad, spielt Geige. " * 8 + "\n\n## Wege\n- Uni: 20 min Rad\n"},
        {"akte": "ziele", "stand": "", "text": ""}],
    "bereiche": [
        {"bereich": "dossiers", "titel": ["umzug", "geige", "fahrrad-werkstatt"]},
        {"bereich": "notizen", "titel": ["wegzeiten"]},
        {"bereich": "kataloge", "titel": ["ideen"]},
        {"bereich": "quellen", "titel": []},
        {"bereich": "vorlagen", "titel": ["dossier", "katalog"]}],
    "skills": [
        {"name": "kurz", "beschreibung": "Wenn Sasha eine schnelle Auskunft will.",
         "status": "aktiv", "herkunft": "sasha", "erstellt": "2026-10-07"},
        {"name": "recherche", "beschreibung": "Wenn etwas im Netz nachgesehen und "
         "mit Quellen belegt werden soll.", "status": "aus", "herkunft": "sasha",
         "erstellt": "2026-10-07"},
        {"name": "wochenplan", "beschreibung": "Wenn die Woche geplant wird.",
         "status": "vorgeschlagen", "herkunft": "ki", "erstellt": "2026-10-07"},
        # 2026-10-07: Anthropic-Skill, aus, mit „braucht" (Gedächtnis-Ansicht).
        {"name": "webapp-testing", "beschreibung": "Toolkit for interacting with and "
         "testing local web applications using Playwright.", "status": "aus",
         "herkunft": "anthropic", "erstellt": "2026-10-07",
         "braucht": "einen Browser, den die KI steuern kann, und Netz zur getesteten Seite"}]}
# Erfundene Ablage (Phase 5, 2026-10-07): ein Dokument mit zwei Fassungen,
# ein Bild-Anhang.
_ABLAGE = {"dokumente": [
    {"id": "d1", "titel": "Packliste Radtour", "art": "markdown", "herkunft": "ki",
     "fassung": 2, "geaendert": "2026-10-06T09:00:00+00:00", "gespraech_titel": "Fahrradschlauch",
     "gespraech": "g1"},
    {"id": "d2", "titel": "skizze.png", "art": "bild", "herkunft": "anhang",
     "fassung": 1, "geaendert": "2026-10-04T09:00:00+00:00"}]}
_DOK = {"kopf": {"id": "d1", "titel": "Packliste Radtour", "art": "markdown", "fassung": 2},
        "fassung": 2, "bytes": 300, "pfad": "/x/v2-pc.md",
        "inhalt": "# Packliste\n\n" + "\n".join("- Ding Nummer %d" % i for i in range(40))}


# Erfundene Projekte (Claude-Web-Plan Phase 6, 2026-10-07).
_PROJEKTE = {"projekte": [
    {"id": "geige", "name": "Geige", "wissen": 2, "archiviert": False},
    {"id": "umzug-berlin", "name": "Umzug Berlin", "wissen": 0, "archiviert": False}]}
_PROJEKT_GEIGE = {
    "id": "geige", "name": "Geige", "archiviert": False, "stand": "p1",
    "anweisungen": "# Wie ich übe\n\n- Immer mit Fingersätzen antworten.\n"
                   "- Stücke nach Schwierigkeit ordnen.\n",
    "wissen": [{"name": "noten.md", "groesse": 2300}, {"name": "uebeplan.txt", "groesse": 640}],
    "gespraeche": [
        {"id": "g2", "titel": "Partita üben, Satz 3", "letzte": "2026-10-05T08:00:00+00:00"},
        {"id": "g0", "titel": "Bogenhaltung", "archiviert": True,
         "letzte": "2026-09-01T08:00:00+00:00"}]}


# Customize (2026-10-07): Kosten, was die KI kann, Wege.
_KOSTEN = {"heute": 0.12, "monat": 3.12, "calls_heute": 7, "geschaetzt_monat": 0.04,
           "modelle": {"claude-sonnet-5": 2.9, "qwen-plus": 0.22},
           "budget": {"status": "ok", "ausgegeben": 3.12, "limit": 20.0, "anteil": 0.156}}
_WERKZEUGE = {"werkzeuge": [
    {"name": "read_calendar", "alltag": "kalender lesen", "beschreibung": "Termine eines Tages lesen",
     "fragt": "nie", "schienen": ["klein", "gross"]},
    {"name": "add_calendar_entry", "alltag": "termine eintragen",
     "beschreibung": "Einen Termin in den Kalender schreiben", "fragt": "immer",
     "schienen": ["klein", "gross"]},
    {"name": "read_note", "alltag": "notizen lesen", "beschreibung": "Eine Notiz aus dem Gedächtnis lesen",
     "fragt": "nie", "schienen": ["klein", "gross"]},
    {"name": "web_search", "alltag": "im internet suchen", "beschreibung": "Im Netz suchen",
     "fragt": "manchmal", "schienen": ["gross"]},
    {"name": "run_code", "alltag": "programme abgeschottet ausführen",
     "beschreibung": "Python oder Shell in einem abgeschotteten Ordner", "fragt": "immer",
     "schienen": ["gross"]}]}
_WEGE = {"cloud_enabled": True, "local_enabled": False}


def _synth(path):
    """Erfundene Mail-Daten: die echten gehen nie live (Seen-Flag), aber das
    Post-Panel soll im Vergleich auch mit Mails gezeichnet werden."""
    if path.startswith("/api/graphs/reminders"):
        if os.path.exists(os.environ.get("ZTUI_NAG_DATEI", "")):
            return [{"id": "g_x", "name": "schlaf", "remind_at": "20:00"},
                    {"id": "g_y", "name": "stimmung"}]
        return None
    if path == "/api/ai/einstellungen":      # Chat-Befehle /modell, /effort
        return _EINSTELLUNGEN
    if path == "/api/erlaubnis":
        return _ERLAUBNIS
    if path == "/api/ai/kosten":
        return _KOSTEN
    if path == "/api/ai/werkzeuge":
        return _WERKZEUGE
    if path == "/api/ai/backends":
        return _WEGE
    if path == "/api/gespraeche":
        return _GESPRAECHE
    if path.startswith("/api/gespraeche?archiv"):
        return _ARCHIV
    if path == "/api/gedaechtnis":
        return _GEDAECHTNIS
    if path.startswith("/api/ablage/"):
        return _DOK
    if path.startswith("/api/ablage"):
        return _ABLAGE if "archiv" not in path else {"dokumente": []}
    if path.startswith("/api/projekte?archiv"):
        return {"projekte": []}
    if path == "/api/projekte":
        return _PROJEKTE
    if path == "/api/projekte/geige":
        return _PROJEKT_GEIGE
    if path.startswith("/api/chat/history"):
        return _VERLAUF
    if path.startswith(("/api/mail/folder?", "/api/mail/inbox?")) or path == "/api/mail/inbox":
        return _MAILS
    if path.startswith(("/api/mail/body?", "/api/mail/inbox-body?")):
        return _BODY
    return None


def _hole(path):
    s = _synth(path)
    if s is not None:
        return s
    with _lock:
        if path in _cache:
            return _cache[path]
    if NUR_CACHE or path.startswith(NIE_LIVE):
        FEHLT.append(path)
        return {}
    try:
        with urllib.request.urlopen(LIVE + path, timeout=8) as r:
            body = r.read().decode("utf-8")
        obj = json.loads(body)
    except Exception as e:  # noqa
        obj = {}
    with _lock:
        _cache[path] = obj
        with open(CACHE + ".tmp", "w") as f:
            json.dump(_cache, f)
        os.replace(CACHE + ".tmp", CACHE)
    return obj


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        self._send(_hole(self.path))

    def _drain(self):
        try:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
        except (ValueError, OSError):
            pass

    def _denken_strom(self):
        """POST /api/chat für die Denk-Animation (2026-10-07): ZTUI_DENK_S
        Sekunden lang Denk-Stücke, ein Werkzeug, dann die Antwort."""
        import time as _time
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        def ev(obj):
            self.wfile.write(("data: %s\n\n" % json.dumps(obj)).encode())
            self.wfile.flush()
        try:
            ev({"strom": "s1"})
            ende = _time.monotonic() + float(os.environ.get("ZTUI_DENK_S", "12"))
            while _time.monotonic() < ende:
                ev({"reflect": "ich überlege, wie man unterwegs flickt … "})
                _time.sleep(0.5)
            ev({"werkzeug": {"phase": "start", "name": "read_note", "args": {"name": "fahrrad"}}})
            ev({"werkzeug": {"phase": "fertig", "name": "read_note", "text": "Flickzeug: Satteltasche"}})
            ev({"token": "Loch suchen, anrauen, Kleber, kurz warten, Flicken drauf."})
            _time.sleep(0.3)
            ev({"done": True})
        except OSError:
            pass

    def do_POST(self):
        self._drain()
        if self.path == "/api/chat":
            self._denken_strom()
            return
        if self.path == "/api/projekte/zuordnen":     # /projekt (Phase 6)
            self._send({"gespraech": "g1", "projekt": "geige", "name": "Geige"})
            return
        self._send({})

    do_PUT = do_POST
    do_DELETE = do_POST


if __name__ == "__main__":
    port = int(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.serve_forever()
