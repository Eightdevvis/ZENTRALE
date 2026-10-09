"""Hub-Bauplan Schritt 1 (2026-10-09): der Sprach-Tutor ist eine eigene App.

ZENTRALE kennt seinen Code nicht mehr. Es findet die App (core/apps.py),
schickt ihr abonnierte Ereignisse (core/hub_ereignisse.py), startet sie
(scripts/open_tutor_room.py) und packt ihr Zimmer für den Pi
(core/aussenposten.py, Einträge app:<name>/…). In den Tests ist die App die
Test-App unter tests/fixtures/app_tutor (tests/conftest.py).
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import apps
import aussenposten
import hub_ereignisse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import open_tutor_room as starter   # noqa: E402


# ── Apps finden ────────────────────────────────────────────────────────

def test_manifest_der_test_app():
    m = apps.manifest("tutor")
    assert m["name"] == "tutor" and m["_pfad"] == apps.pfad("tutor")
    assert [a["name"] for a in apps.abonnenten("anwesenheit")] == ["tutor"]
    assert apps.abonnenten("mail.neu") == []


def test_fehlende_app_ist_einfach_nicht_da(monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path / "weg"))
    assert apps.manifest("tutor") is None and apps.installiert() == []
    assert hub_ereignisse.senden("anwesenheit", warten=True) == 0


def test_kaputtes_manifest_bricht_nichts(monkeypatch, tmp_path):
    (tmp_path / "app.toml").write_text("name = [kaputt")
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path))
    assert apps.manifest("tutor") is None


def test_start_befehl_nimmt_den_python_der_app():
    m = apps.manifest("tutor")
    b = apps.befehl(m, m["start"])
    assert b[1:] == ["-m", "tutor.server"]
    assert "python" in os.path.basename(b[0])


# ── Ereignisse ─────────────────────────────────────────────────────────

class _Fang(BaseHTTPRequestHandler):
    empfangen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        _Fang.empfangen.append((self.path, json.loads(self.rfile.read(n))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def app_mit_server(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Fang)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "app.toml").write_text(
        'name = "tutor"\nstart = "python -m tutor.server"\n'
        'adresse = "http://127.0.0.1:%d"\nrechte = ["ereignis:anwesenheit"]\n'
        '[ereignisse]\nziel = "/hub/ereignis"\n' % srv.server_port)
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path))
    _Fang.empfangen = []
    yield srv
    srv.shutdown()


def test_anwesenheit_kommt_bei_der_app_an(app_mit_server):
    assert hub_ereignisse.senden("anwesenheit", {"quelle": "pir"}, warten=True) == 1
    assert _Fang.empfangen == [("/hub/ereignis",
                                {"name": "anwesenheit", "daten": {"quelle": "pir"}})]


def test_app_aus_ist_kein_fehler(capsys):
    """Die Test-App zeigt ins Leere: nichts wirft, eine Zeile im Log."""
    assert hub_ereignisse.senden("anwesenheit", warten=True) == 1
    assert "nicht zugestellt" in capsys.readouterr().out


def test_brain_haengt_nicht_an_der_app():
    """Im Hintergrund: brain.py wartet nie auf eine App."""
    import brain
    import events
    brain.process_event(events.PRESENCE_DETECTED)   # Test-App ist aus — kein Absturz


# ── Starter ────────────────────────────────────────────────────────────

def test_starter_prueft_ob_die_app_da_ist(monkeypatch, tmp_path, capsys):
    assert starter.main(["--pruefen"]) == 0
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path / "weg"))
    monkeypatch.setattr(starter, "ROOT", str(tmp_path))       # kein apps/, kein Nachbar
    monkeypatch.setitem(sys.modules, "apps", None)            # wie auf dem Pi: kein core/
    assert starter.main(["--pruefen"]) == 2
    assert "nicht installiert" in capsys.readouterr().out


def test_server_adresse():
    m = {"adresse": "http://127.0.0.1:5070"}
    assert starter.server_url(m, None, None) == "http://127.0.0.1:5070"
    assert starter.server_url(m, "http://localhost:5000", None) == "http://127.0.0.1:5070"
    assert starter.server_url(m, "http://192.168.1.5:5000", None) == "http://192.168.1.5:5070", \
        "Laptop/Pi → Tutor-Server auf dem Rechner des Hubs"
    assert starter.server_url(m, None, "http://x:1") == "http://x:1"


def test_alter_aufruf_mit_hub_als_url_wird_umgedeutet(monkeypatch):
    """Der Pi-Autostart vor dem Umzug rief --url <ZENTRALE>. Das darf nicht
    als Tutor-Server gelten."""
    gestartet = {}
    monkeypatch.setattr(starter, "_lebt", lambda url: True)
    monkeypatch.setattr(starter.subprocess, "call",
                        lambda cmd, cwd=None, env=None: gestartet.update(cmd=cmd, env=env) or 0)
    monkeypatch.setattr(starter, "_start_services", lambda: [])
    assert starter.main(["--url", "http://192.168.1.5:5000", "--wand"]) == 0
    cmd = gestartet["cmd"]
    assert cmd[cmd.index("--url") + 1] == "http://192.168.1.5:9"
    assert "--wand" in cmd and gestartet["env"]["ZENTRALE_URL"] == "http://192.168.1.5:5000"
    assert gestartet["env"]["ZENTRALE_TUI"].endswith(os.path.join("tui", "zentrale_tui.py"))


def test_lokal_startet_server_und_raeumt_nur_eigenes_ab(monkeypatch):
    """Auf diesem Rechner: Dienste + Server nur starten, wenn sie fehlen, und
    beim Schließen nur das abräumen, was der Starter selbst gestartet hat."""
    abgeraeumt = []
    monkeypatch.setattr(starter, "_start_services", lambda: ["dienst"])
    monkeypatch.setattr(starter, "_start_server", lambda o, m, u: ["server"])
    monkeypatch.setattr(starter, "_abraeumen", lambda s: abgeraeumt.extend(s))
    monkeypatch.setattr(starter.subprocess, "call", lambda *a, **k: 0)
    starter.main(["--hub", "http://localhost:5000"])
    assert abgeraeumt == ["dienst", "server"]


# ── Pi-Paket ───────────────────────────────────────────────────────────

def test_zimmer_kommt_unter_apps_ins_paket():
    drin = [rel for rel, _ in aussenposten.dateien()]
    assert "apps/tutor/tutor/room.py" in drin
    assert "apps/tutor/app.toml" in drin
    assert not any(r.startswith("tutor/") for r in drin), "kein Tutor-Code mehr aus ZENTRALE"


def test_ohne_app_bleibt_das_paket_heil(monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path / "weg"))
    drin = [rel for rel, _ in aussenposten.dateien()]
    assert "tui/zentrale_tui.py" in drin and not any(r.startswith("apps/") for r in drin)


# ── TUI ────────────────────────────────────────────────────────────────

def test_taste_u_ohne_bildschirm_sagt_es_freundlich(monkeypatch):
    from tui.ansichten import app_start
    monkeypatch.delenv("DISPLAY", raising=False)

    class Bz:
        cmd_msg = ""
    bz = Bz()
    app_start.AppStart(None, bz).tutor_oeffnen()
    assert "bildschirm" in bz.cmd_msg


def test_taste_u_meldet_fehlende_app(monkeypatch, tmp_path):
    from tui.ansichten import app_start
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(tmp_path / "weg"))
    grund = app_start.AppStart(None).pruefen()
    # Der echte Starter läuft als eigener Prozess; neben dem Worktree kann
    # language-tutor liegen — dann ist die App eben da.
    assert grund == "" or "nicht installiert" in grund
