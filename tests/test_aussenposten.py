"""Aussenposten-Pakete: was rausgeht, und dass ein Knoten es heil einbaut.

Ein Aussenposten hostet kein Backend (memory/system/topologie.md). Er bekommt
kein git-Checkout mehr, sondern ein zugeschnittenes Paket aus der Positivliste
`deploy/aussenposten.txt`, das er sich per HTTP selbst abholt.

Hier wird beides gegen einen echten Miniatur-Server geprueft: schnueren
(core/aussenposten.py) und einbauen (scripts/aussenposten_update.py) — nicht
gegen Attrappen, weil genau das Zusammenspiel der beiden Seiten die Stelle
ist, an der so etwas kaputtgeht.
"""

import http.server
import json
import os
import subprocess
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import aussenposten            # type: ignore  – der Schnuerer (core/)
import aussenposten_update as updater  # type: ignore  – der Knoten (scripts/)

UPDATER = os.path.join(ROOT, "scripts", "aussenposten_update.py")


# ── Der Schnuerer ────────────────────────────────────────────────────────

def test_liste_nennt_nur_vorhandenes():
    """Jeder Eintrag der Positivliste existiert auch wirklich."""
    for eintrag in aussenposten.liste_lesen():
        assert os.path.exists(os.path.join(ROOT, eintrag)), eintrag


def test_paket_bleibt_klein_und_ohne_backend():
    """Der Sinn der Liste: das Backend bleibt draussen.

    Faellt jemand zurueck auf den Vollspiegel, schlaegt das hier an — vorher
    landeten data/tts_model/ (1,0 GB) und core/map/ (29 MB) auf der SD-Karte.
    """
    drin = [rel for rel, _ in aussenposten.dateien()]
    assert drin, "Paket ist leer"
    for verboten in ("ui/", "services/", "data/", "core/map/", "tests/"):
        assert not any(r.startswith(verboten) for r in drin), verboten
    # core/ nur als einzelne, backend-freie Datei (host_metrics fuer Telemetrie)
    assert [r for r in drin if r.startswith("core/")] == ["core/host_metrics.py"]
    assert aussenposten.manifest()["bytes"] < 5 * 1024 * 1024


def test_version_haengt_am_inhalt(tmp_path):
    """Gleicher Inhalt -> gleiche Version; eine Aenderung faellt auf."""
    vorher = aussenposten.manifest()["version"]
    assert aussenposten.manifest()["version"] == vorher

    hilfs = tmp_path / "repo"
    (hilfs / "deploy").mkdir(parents=True)
    (hilfs / "tui").mkdir()
    (hilfs / "deploy" / "aussenposten.txt").write_text("tui/x.py\n")
    (hilfs / "tui" / "x.py").write_text("a = 1\n")
    ap_liste = str(hilfs / "deploy" / "aussenposten.txt")

    def version():
        echt, aussenposten.LISTE = aussenposten.LISTE, ap_liste
        try:
            return aussenposten.manifest(str(hilfs))["version"]
        finally:
            aussenposten.LISTE = echt

    v1 = version()
    (hilfs / "tui" / "x.py").write_text("a = 2\n")
    assert version() != v1, "Inhaltsaenderung muss die Version bewegen"


def test_paket_ist_byte_gleich():
    """Zweimal schnueren = dieselben Bytes (sortiert, mtime=0).

    Ohne das stuende die Bauzeit im Archiv und jeder Knoten wuerde bei jedem
    Lauf ein 'neues' Paket sehen.
    """
    assert aussenposten.paket() == aussenposten.paket()


# ── Der Knoten ───────────────────────────────────────────────────────────

@pytest.fixture
def backend():
    """Miniatur-Backend, das Manifest und Paket ausliefert wie ui/app.py."""
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.endswith("/manifest"):
                koerper = json.dumps(aussenposten.manifest()).encode()
                typ, extra = "application/json", {}
            elif self.path.endswith("/paket"):
                koerper = aussenposten.paket()
                typ = "application/gzip"
                extra = {"X-Paket-Version": aussenposten.manifest()["version"]}
            else:
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(koerper)))
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(koerper)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _lauf(url, ziel, *extra):
    r = subprocess.run(
        [sys.executable, UPDATER, "--url", url, "--ziel", str(ziel),
         "--log", os.path.join(str(ziel), "update.log"), *extra],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


def test_knoten_installiert_und_wiederholt_sich_nicht(backend, tmp_path):
    ziel = tmp_path / "knoten"
    ziel.mkdir()

    assert "neue Version" in _lauf(backend, ziel)
    assert (ziel / "tutor" / "room.py").exists()
    assert (ziel / "tui" / "zentrale_tui.py").exists()
    assert not (ziel / "ui").exists(), "Backend-Code darf nicht mitkommen"

    # Zweiter Lauf: gleiche Version -> gar nichts. Das ist der Normalfall,
    # alle fuenf Minuten, jahrelang.
    assert _lauf(backend, ziel) == ""


def test_neu_repariert_veraenderte_datei(backend, tmp_path):
    """Der normale Lauf vergleicht nur Versionen und merkt lokalen Schaden
    NICHT. Dafuer gibt es --neu."""
    ziel = tmp_path / "knoten"
    ziel.mkdir()
    _lauf(backend, ziel)

    (ziel / "tutor" / "room.py").write_text("kaputt")
    assert _lauf(backend, ziel) == "", "Version stimmt -> kein Eingriff"
    assert (ziel / "tutor" / "room.py").read_text() == "kaputt"

    _lauf(backend, ziel, "--neu")
    assert (ziel / "tutor" / "room.py").read_text().startswith("#!")


def test_karteileichen_verschwinden(backend, tmp_path):
    """Was im Vorgaengerpaket war und jetzt nicht mehr, wird entfernt —
    sonst sammelt ein Knoten ueber Jahre tote Dateien an."""
    ziel = tmp_path / "knoten"
    ziel.mkdir()
    _lauf(backend, ziel)

    stand_pfad = ziel / ".aussenposten_stand.json"
    stand = json.loads(stand_pfad.read_text())
    (ziel / "scripts" / "alt.py").write_text("alt")
    stand["dateien"].append("scripts/alt.py")
    stand["version"] = "erzwinge-neu"
    stand_pfad.write_text(json.dumps(stand))

    _lauf(backend, ziel)
    assert not (ziel / "scripts" / "alt.py").exists()


def test_backend_weg_ist_kein_absturz(tmp_path):
    """Knoten laeuft, PC ist aus: leise scheitern, beim naechsten Mal wieder.
    Ein Cron-Job, der bei jedem Ausfall Fehler wirft, ist unbrauchbar."""
    ziel = tmp_path / "knoten"
    ziel.mkdir()
    aus = _lauf("http://127.0.0.1:9", ziel)
    assert "nicht erreichbar" in aus
    assert not (ziel / "tutor").exists()


@pytest.mark.parametrize("boese", [
    "../../etc/passwd", "/etc/passwd", "a/../../b", "../x",
])
def test_ausbruch_aus_dem_zielordner_blockiert(boese):
    """Ein tar darf '..' oder absolute Pfade enthalten und beim Auspacken
    aus dem Zielordner ausbrechen. Diese Namen kommen nie durch."""
    assert not updater.sicher(boese)


@pytest.mark.parametrize("gut", [
    "tui/zentrale_tui.py", "core/host_metrics.py", "tutor/room.py",
])
def test_normale_pfade_gehen_durch(gut):
    assert updater.sicher(gut)


# ── Abhaengigkeiten ──────────────────────────────────────────────────────
#
# Ein Paket ist erst nutzbar, wenn auch seine Pakete da sind. Frueher lief pip
# NUR bei geaenderter Requirements-Datei — auf einem frisch bespielten Knoten
# aendert die sich aber nicht (sie kommt fertig mit), also blieb der venv leer
# und das Zimmer startete nie. Jetzt zaehlt zusaetzlich, was FEHLT.

def test_requirements_werden_gelesen():
    req = os.path.join(ROOT, "deploy", "requirements-aussenposten.txt")
    namen = updater._gefordert(req)
    assert "pygame" in namen and "sounddevice" in namen
    assert "webrtcvad-wheels" in namen
    # Kommentarzeilen und die NICHT-hier-Liste duerfen nicht mitkommen
    assert not any(n.startswith("#") for n in namen)
    for backend_paket in ("faster-whisper", "flask", "sherpa-onnx", "openai"):
        assert backend_paket not in namen, backend_paket


@pytest.mark.parametrize("roh,erwartet", [
    ("webrtcvad_wheels", "webrtcvad-wheels"),
    ("WebRTCVAD-Wheels", "webrtcvad-wheels"),
    ("pygame", "pygame"),
])
def test_paketnamen_werden_normalisiert(roh, erwartet):
    """PEP 503: Gross/Klein und -_. sind beim Vergleich egal. Ohne das haelt
    der Updater ein installiertes 'webrtcvad_wheels' fuer fehlend und ruft bei
    jedem Lauf pip."""
    assert updater._normal(roh) == erwartet


def test_fehlende_pakete_werden_erkannt(tmp_path):
    req = tmp_path / "req.txt"
    req.write_text("# Kommentar\npytest\ngibtesnichtxyz>=1.0\n\n")
    fehlt = updater._fehlende(sys.executable, str(req))
    assert "gibtesnichtxyz" in fehlt      # nicht installiert
    assert "pytest" not in fehlt          # laeuft ja gerade


def test_unlesbarer_interpreter_meldet_alles_fehlend(tmp_path):
    """Laesst sich der venv nicht befragen, wird lieber installiert als
    stillschweigend nichts zu tun."""
    req = tmp_path / "req.txt"
    req.write_text("pygame\n")
    assert updater._fehlende("/gibt/es/nicht", str(req)) == ["pygame"]


def test_abgleich_installiert_auch_wenn_paket_aktuell_ist(backend, tmp_path, monkeypatch):
    """Der zweite Lauf darf die Pakete nicht ueberspringen.

    Genau das ist am Pi passiert: erster Lauf installierte das Paket, ab dem
    zweiten stimmte die Version, der Updater stieg frueh aus — und der venv
    blieb fuer immer leer. Ein Abgleich muss den SOLL-Zustand herstellen,
    nicht nur Aenderungen nachfahren.
    """
    ziel = tmp_path / "knoten"
    ziel.mkdir()
    _lauf(backend, ziel)                       # installiert, Version steht
    assert _lauf(backend, ziel) == ""          # nichts zu tun (kein venv da)

    # Jetzt einen venv vortaeuschen, in dem etwas fehlt, und pip mitschreiben.
    gerufen = tmp_path / "pip-aufruf.txt"
    venv_bin = ziel / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/bin/sh\nexec %s \"$@\"\n" % sys.executable)
    (venv_bin / "pip").write_text(
        "#!/bin/sh\necho \"$@\" >> %s\n" % gerufen)
    for f in ("python", "pip"):
        os.chmod(venv_bin / f, 0o755)

    req = ziel / "deploy" / "requirements-aussenposten.txt"
    req.write_text("gibtesnichtxyz\n")         # garantiert nicht installiert

    _lauf(backend, ziel)
    assert gerufen.exists(), "pip wurde nicht gerufen, obwohl ein Paket fehlt"
    assert "requirements-aussenposten.txt" in gerufen.read_text()


def test_installiert_aber_nicht_ladbar_wird_gemeldet(tmp_path):
    """Ein Wheel kann installiert sein und beim Import trotzdem an einer
    fehlenden C-Bibliothek scheitern — pygame ohne libSDL2, sounddevice ohne
    PortAudio. `pip list` sieht davon nichts; am Pi war genau das der Fall."""
    req = tmp_path / "req.txt"
    # 'this' ist immer importierbar, 'antigravity' oeffnet nur einen Browser —
    # wir brauchen etwas, das SICHER beim Import kracht:
    (tmp_path / "kaputtesmodul.py").write_text("raise ImportError('libFoo.so fehlt')\n")
    req.write_text("kaputtesmodul\nsys\n")
    monkey = dict(os.environ, PYTHONPATH=str(tmp_path))
    import subprocess as sp
    r = sp.run([sys.executable, "-c", "import kaputtesmodul"],
               capture_output=True, text=True, env=monkey)
    assert r.returncode != 0                      # Vorbedingung des Tests

    alt = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(tmp_path)
    try:
        kaputt = dict(updater._nicht_ladbar(sys.executable, str(req)))
    finally:
        if alt is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = alt

    assert "kaputtesmodul" in kaputt
    assert "libFoo.so" in kaputt["kaputtesmodul"]
    assert "sys" not in kaputt                    # laesst sich laden


def test_systemliste_nennt_die_bekannten_bibliotheken():
    """Die apt-Liste ist Doku fuer Menschen — aber sie muss die zwei Faelle
    nennen, die am Pi wirklich gefehlt haben."""
    pfad = os.path.join(ROOT, "deploy", "aussenposten-system.txt")
    inhalt = open(pfad, encoding="utf-8").read()
    assert "libsdl2-2.0-0" in inhalt             # pygame
    assert "libportaudio2" in inhalt             # sounddevice
