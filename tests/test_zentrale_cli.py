"""Der Befehl `zentrale` (zentrale_cli/): Hilfe, Fassung, Einrichtungs-
Assistent mit gespieltem Terminal gegen eine gespielte Cloud, Geräte,
Hardware-Erkennung. Nie die echte konto.json, nie Sashas data/."""
import io
import json
import os
import subprocess
import sys

import pytest

import ai_config
import dateien
import knoten
import konto
import konto_schluessel as ks
from _falsche_cloud import FalscheCloud
from zentrale_cli import befehle, haupt
from zentrale_cli.ausgabe import Terminal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "ein-langes-passwort"


def _laufen(*args, **env):
    umgebung = dict(os.environ, PYTHONPATH=ROOT, **env)
    return subprocess.run([sys.executable, "-m", "zentrale_cli", *args], capture_output=True,
                          text=True, env=umgebung, cwd=ROOT, timeout=60)


def test_hilfe_gruppen_beispiele_ohne_farbe_wenn_kein_terminal():
    r = _laufen("--help")
    assert r.returncode == 0
    for teil in ("Usage", "Account", "account create", "account recover", "devices",
                 "update", "Examples", "zentrale setup"):
        assert teil in r.stdout
    assert "\x1b[" not in r.stdout


def test_farbe_nur_am_terminal_und_ohne_no_color(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert Terminal(aus=Tty()).farbig
    monkeypatch.setenv("NO_COLOR", "1")
    assert not Terminal(aus=Tty()).farbig
    assert not Terminal(aus=io.StringIO()).farbig


def test_version_und_unbekannter_befehl():
    r = _laufen("version")
    assert r.returncode == 0 and r.stdout.startswith("ZENTRALE ")
    r = _laufen("tanzen")
    assert r.returncode == 2 and "Unknown command" in r.stderr


# ── Assistent ──────────────────────────────────────────────────────────

class Spiel(Terminal):
    def __init__(self, *antworten):
        super().__init__(aus=io.StringIO(), ein=io.StringIO("".join(a + "\n" for a in antworten)))

    @property
    def text(self):
        return self.aus.getvalue()


@pytest.fixture
def geraet(monkeypatch, tmp_path):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(dateien, "knoten", lambda: "minipc")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "abgleich"))
    monkeypatch.setattr(ai_config, "_CONFIG_PATH", str(tmp_path / "ai_config.json"))
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_overrides", {})
    wurzel = tmp_path / "hub"
    (wurzel / "data").mkdir(parents=True)
    monkeypatch.setattr(befehle, "WURZEL", str(wurzel))
    c.tmp, c.wurzel = tmp_path, wurzel
    yield c
    c.stopp()


def _einstellungen(geraet):
    with open(geraet.tmp / "ai_config.json", encoding="utf-8") as f:
        return json.load(f)


def test_assistent_konto_anlegen_auswaehlen_und_wahl_bleibt(geraet):
    from zentrale_cli import assistent
    term = Spiel("2",                                          # neues Konto
                 "ZB-AAAA-BBBB-CCCC-DDDD", "s@x.org", PW, PW, "y",         # Code, Mail, Passwort ×2, gesichert
                 "2",                                          # einzeln wählen
                 "n", "1 5", "")                               # nichts, dann Listen + Gedächtnis
    assert befehle.eingerichtet() is False
    rc = assistent.setup(term)
    assert rc == 0, term.text
    assert "EMERGENCY KEY" in term.text
    e = _einstellungen(geraet)
    assert e["abgleich_bereiche"] == ["lists", "memory"]
    assert e["abgleich_mitte_art"] == "http" and e["abgleich_weg"] == "mitte"
    assert e["einrichtung"]
    assert befehle.eingerichtet()
    assert "minipc" in geraet.zustand.knoten["s@x.org"]           # Gerät gemeldet
    assert geraet.zustand.kopf["s@x.org"] is not None              # gleich abgeglichen
    # Neu geladen (wie nach einem Neustart): die Wahl ist noch da.
    ai_config._overrides.clear()
    ai_config._config.clear()
    ai_config._load()
    import abgleich_bereiche
    assert abgleich_bereiche.gewaehlt() == ["lists", "memory"]


def test_assistent_notfallschluessel_nicht_bestaetigt_kein_konto(geraet):
    from zentrale_cli import assistent
    term = Spiel("2", "ZB-AAAA-BBBB-CCCC-DDDD", "s@x.org", PW, PW, "n")
    assert assistent.setup(term) == 1
    assert not geraet.zustand.konten and not konto.angemeldet()
    assert "ZB-AAAA-BBBB-CCCC-DDDD" in geraet.zustand.codes


def test_assistent_lokal_bleiben(geraet):
    from zentrale_cli import assistent
    term = Spiel("3")
    assert assistent.setup(term) == 0
    e = _einstellungen(geraet)
    assert e["einrichtung"] and "abgleich_mitte_art" not in e
    assert not geraet.zustand.aufrufe                             # kein Wort zur Cloud


def test_erster_start_ohne_einrichtung_erst_assistent_dann_tui(geraet, monkeypatch):
    gestartet = []
    monkeypatch.setattr(befehle, "tui", lambda term: gestartet.append(1) or 0)
    monkeypatch.setattr(haupt, "_entwickler_checkout", lambda: False)
    term = Spiel("3")
    assert haupt.main([], term=term) == 0
    assert "first start" in term.text and gestartet == [1]
    term = Spiel()
    assert haupt.main([], term=term) == 0 and "first start" not in term.text


def test_login_falsches_passwort_ein_satz_kein_traceback(geraet):
    konto.anlegen(konto.Entwurf(PW), "s@x.org", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    konto.abmelden()
    term = Spiel("s@x.org", "falsch-falsch-falsch")
    assert haupt.main(["login"], term=term) == 1
    assert "Wrong email or password" in term.text and "Traceback" not in term.text


def test_devices_meldet_sich_selbst_und_listet(geraet, monkeypatch):
    konto.anlegen(konto.Entwurf(PW), "s@x.org", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    term = Spiel()
    assert befehle.devices(term) == 0
    b = geraet.zustand.knoten["s@x.org"]["minipc"]
    assert b["name"] == "minipc" and b["sorte"] == "vollknoten"
    assert set(b["hardware"]) == {"gpu", "bildschirm", "mikro", "lautsprecher"}
    assert "minipc" in term.text and "(this device)" in term.text


def test_status_ohne_konto(geraet):
    term = Spiel()
    assert befehle.status(term) == 0
    assert "not logged in" in term.text


def test_hardware_wird_erkannt_nicht_gefragt(tmp_path):
    (tmp_path / "proc/asound").mkdir(parents=True)
    (tmp_path / "proc/asound/pcm").write_text(
        "00-00: ALC : ALC : playback 1 : capture 1\n")
    karte = tmp_path / "sys/class/drm/card1/device"
    karte.mkdir(parents=True)
    (karte / "vendor").write_text("0x10de\n")
    (tmp_path / "sys/class/drm/card1-HDMI-A-1").mkdir()
    (tmp_path / "sys/class/drm/card1-HDMI-A-1/status").write_text("connected\n")
    assert knoten.hardware(str(tmp_path), umgebung={}) == \
        {"gpu": True, "bildschirm": True, "mikro": True, "lautsprecher": True}
    leer = tmp_path / "leer"
    leer.mkdir()
    assert knoten.hardware(str(leer), umgebung={}) == \
        {"gpu": False, "bildschirm": False, "mikro": False, "lautsprecher": False}
