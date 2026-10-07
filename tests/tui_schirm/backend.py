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
         "modelle": ["qwen-plus", "qwen-turbo"]}]}


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

    def do_POST(self):
        self._drain(); self._send({})

    do_PUT = do_POST
    do_DELETE = do_POST


if __name__ == "__main__":
    port = int(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.serve_forever()
