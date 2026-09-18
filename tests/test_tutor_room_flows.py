"""Zimmer-Flows headless gegen ein Fake-Backend (pygame im Dummy-Treiber).

Sasha 2026-09-18: »denk dir Tests aus« — vor allem, dass Menüs und Spielstände
tun, was abgemacht ist: Esc im Spiel = Zwischenmenü (Session friert nur ein),
Hauptmenü = Session zu, Esc im Hauptmenü = »Tutor schließen?«, ein neuer
Spielstand bringt Sprache/Persona/Stimme des Zimmers mit.

Gefahren werden echte Tastendrücke durch den echten Render-Loop; das
Fake-Backend protokolliert jede Anfrage. Läuft ohne Bildschirm und ohne Ton.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

LANGS = [{"code": "es", "name": "Spanisch", "enabled": True, "persona_name": "Lucía", "country": "Spanien"},
         {"code": "de", "name": "Deutsch", "enabled": True, "persona_name": "Lena", "country": "Deutschland"}]
PERSONA = {"es": "Lucía", "de": "Lena"}


class FakeBackend:
    """Minimales /api/tutor/*: hält Stände + aktive Sprache, loggt POSTs."""

    def __init__(self):
        self.posts = []
        self.state = {"aktiv": "es-1", "lang": "es",
                      "staende": [{"id": "es-1", "name": "Erster", "lang": "es", "level": 0,
                                   "woerter": 3, "muenzen": 0, "zuletzt": "b", "erstellt": "a"}]}
        self.active = True
        st = self.state
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, d, code=200):
                b = json.dumps(d).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                p = self.path.split("?")[0]
                if p == "/api/tutor/status":
                    return self._json({"present": True, "available": True, "active": outer.active, "tts": True})
                if p == "/api/tutor/config":
                    return self._json({"present": True, "lang": st["lang"], "persona_name": PERSONA[st["lang"]],
                                       "avatar": "lucia", "langs": LANGS, "providers": [], "provider": "qwen",
                                       "model": "qwen-plus", "native": "en", "natives": ["en", "de"]})
                if p == "/api/tutor/room_state":
                    return self._json({"stance": "idle", "face": "neutral", "battery": 60, "mood": "ok",
                                       "active": outer.active, "mode": "room", "core_got": 0, "core_total": 76,
                                       "core_ratio": 0.0, "tts_speed": 1.0})
                if p == "/api/tutor/staende":
                    return self._json({"present": True, "aktiv": st["aktiv"], "staende": st["staende"]})
                if p == "/api/tutor/assessment":
                    return self._json({"present": True, "lang": st["lang"], "mode": "room", "queue": [], "game": {}})
                return self._json({}, 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.posts.append((self.path, body))
                if self.path == "/api/tutor/staende":
                    sid = "neu-" + body.get("lang", "?")
                    st["staende"].insert(0, {"id": sid, "name": "Neu", "lang": body["lang"], "level": body["level"],
                                             "woerter": 0, "muenzen": 0, "zuletzt": "z", "erstellt": "z"})
                    st["aktiv"] = sid; st["lang"] = body["lang"]; outer.active = False
                    return self._json({"ok": True, "aktiv": sid, "staende": st["staende"]})
                if self.path == "/api/tutor/staende/waehlen":
                    sid = body["id"]
                    eintrag = next((s for s in st["staende"] if s["id"] == sid), None)
                    if not eintrag:
                        return self._json({"ok": False, "error": "unbekannt"}, 400)
                    st["aktiv"] = sid; st["lang"] = eintrag["lang"]; outer.active = False
                    return self._json({"ok": True, "aktiv": sid, "staende": st["staende"]})
                if self.path == "/api/tutor/stop":
                    outer.active = False
                    return self._json({"ok": True})
                if self.path.startswith("/api/tutor/start") or self.path.startswith("/api/tutor/nudge") \
                        or self.path.startswith("/api/tutor/respond"):
                    outer.active = True
                    b = b'data: {"token": "hola"}\n\ndata: {"done": true}\n\n'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                    return
                if self.path == "/api/speak":
                    return self._json({"error": "kein tts im test"}, 503)
                return self._json({"ok": True})

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()

    def calls(self, prefix):
        return [(p, b) for p, b in self.posts if p.startswith(prefix)]


def key(k):
    return int(k)


RUNNER = r'''
import json, os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, %(root)r)
import pygame
from tutor import room
script = {int(k): v for k, v in json.loads(%(script)r).items()}
frames = %(frames)d
sys.argv = ["room.py", "--fenster", "--w", "960", "--h", "600", "--no-mic", "--url", %(url)r]
frame = {"n": 0}; beobachtet = {}
orig_get = pygame.event.get; orig_flip = pygame.display.flip

def fake_get(*a, **kw):
    frame["n"] += 1
    evs = list(orig_get(*a, **kw))
    for k in script.get(frame["n"], []):
        evs.append(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))
    if frame["n"] >= frames:
        evs.append(pygame.event.Event(pygame.QUIT))
    return evs

def fake_flip():
    S = sys._getframe(1).f_locals.get("S")
    if S is not None:
        with S["lock"]:
            asv = S.get("asv")
            beobachtet.update({"lang": S.get("lang"), "persona": S.get("persona"),
                               "pmenu": S.get("pmenu"), "pause": S.get("pause"),
                               "log_len": len(S.get("log") or []),
                               "asv": None if asv is None else {"phase": asv.get("phase"),
                                                                 "schliessen": bool(asv.get("schliessen"))},
                               "frames": frame["n"]})
    orig_flip()

pygame.event.get = fake_get; pygame.display.flip = fake_flip
room.main()
print("RESULT " + json.dumps(beobachtet))
'''


def fahre(script, url, frames=90):
    """room.main() in einem eigenen Prozess mit skriptierten Tasten (Frame →
    Tasten). Gibt an, was das Zimmer am Ende in S hatte. Eigener Prozess, weil
    pygame im Dummy-Treiber ein zweites init/quit im selben Prozess nicht
    überlebt — und weil es dem echten Betrieb entspricht."""
    import subprocess
    code = RUNNER % {"root": ROOT, "script": json.dumps({str(k): v for k, v in script.items()}),
                     "frames": frames, "url": url}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=ROOT)
    line = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, "kein RESULT — Zimmer abgestürzt?\n" + r.stderr[-2000:]
    return json.loads(line[-1][7:])


@pytest.fixture
def be():
    b = FakeBackend()
    yield b
    b.close()


def test_esc_im_hauptmenue_fragt_und_j_schliesst(be):
    script = {10: [key(pygame.K_ESCAPE)],                       # Zwischenmenü
              14: [key(pygame.K_DOWN), key(pygame.K_RETURN)],   # Hauptmenü
              40: [key(pygame.K_ESCAPE)],                       # »Tutor schließen?«
              44: [key(pygame.K_j)]}                            # ja → Fenster zu
    S = fahre(script, be.url, frames=200)
    assert S["frames"] < 200, "J muss das Fenster schließen — lange vor dem Frame-Limit"
    assert be.calls("/api/tutor/stop"), "Hauptmenü muss die Session beenden"
    assert not [p for p, _ in be.posts if p.startswith("/api/tutor/start")], "kein Start nach dem Schließen"


def test_esc_im_hauptmenue_n_bleibt_im_hauptmenue(be):
    script = {10: [key(pygame.K_ESCAPE)], 14: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              40: [key(pygame.K_ESCAPE)], 44: [key(pygame.K_n)]}
    S = fahre(script, be.url, frames=70)
    asv = S.get("asv")
    assert asv and asv["phase"] == "welcome" and not asv["schliessen"], "nach N: Hauptmenü, Dialog zu"
    assert be.calls("/api/tutor/stop")
    assert not be.calls("/api/tutor/nudge"), "im Hauptmenü darf niemand reden"


def test_neuer_spielstand_bringt_sprache_und_persona_mit(be):
    script = {10: [key(pygame.K_ESCAPE)], 14: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              40: [key(pygame.K_DOWN), key(pygame.K_RETURN)],   # Neuer Spielstand
              46: [key(pygame.K_DOWN), key(pygame.K_RETURN)],   # Deutsch
              52: [key(pygame.K_DOWN), key(pygame.K_RETURN)]}   # Level 1 → anlegen
    S = fahre(script, be.url, frames=110)
    neu = be.calls("/api/tutor/staende")
    assert neu and neu[-1][1] == {"name": "", "lang": "de", "level": 1}
    assert S.get("lang") == "de" and S.get("persona") == "Lena", S
    assert S.get("asv") is None, "nach dem Anlegen zurück im Zimmer"
    assert be.calls("/api/tutor/start"), "der gewählte Stand startet seine Session"
    assert S["log_len"] <= 1, "kein alter Verlauf — höchstens die neue Begrüßung"


def test_stimme_und_stt_folgen_dem_stand(be):
    """Nach dem Wechsel auf de muss /api/speak mit lang=de gerufen werden — nicht
    mehr mit es (Sasha: »Lena spricht Spanisch«)."""
    script = {10: [key(pygame.K_ESCAPE)], 14: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              40: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              46: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              52: [key(pygame.K_RETURN)]}                       # Level 0
    fahre(script, be.url, frames=140)
    speaks = [b for p, b in be.posts if p == "/api/speak"]
    assert speaks, "die Begrüßung des neuen Stands muss gesprochen werden"
    assert all(b.get("lang") == "de" for b in speaks[-1:]), speaks


def test_zwischenmenue_friert_nur_ein_kein_stop(be):
    script = {10: [key(pygame.K_ESCAPE)], 30: [key(pygame.K_ESCAPE)]}   # auf und wieder zu
    S = fahre(script, be.url, frames=60)
    assert not be.calls("/api/tutor/stop"), "Zwischenmenü beendet die Session NICHT"
    assert S.get("pmenu") is None


def test_vorhandenen_stand_waehlen_wechselt_sprache(be):
    be.state["staende"].append({"id": "de-1", "name": "Deutsch alt", "lang": "de", "level": 0,
                                "woerter": 9, "muenzen": 1, "zuletzt": "a", "erstellt": "a"})
    script = {10: [key(pygame.K_ESCAPE)], 14: [key(pygame.K_DOWN), key(pygame.K_RETURN)],
              40: [key(pygame.K_DOWN), key(pygame.K_RETURN)]}   # zweite Zeile = de-1
    S = fahre(script, be.url, frames=100)
    assert be.calls("/api/tutor/staende/waehlen")[-1][1] == {"id": "de-1"}
    assert S.get("lang") == "de" and S.get("persona") == "Lena"
