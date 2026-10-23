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


# ── Cloud-Nutzung (core/cloud_nutzung.py, GET /v1/nutzung) ──────────────

def _bericht(*stufen):
    """Ein Bericht wie vom Worker: R2-Speicher und Worker-Anfragen."""
    g = [
        {"id": "worker_anfragen", "name": "Worker requests", "used": 60000, "limit": 100000,
         "unit": "requests", "period": "day", "percent": 60.0, "level": "50", "source": "self",
         "self": 60000, "cloudflare": None, "cloudflare_at": None, "costs_money": False},
        {"id": "r2_speicher", "name": "R2 storage", "used": 8_200_000_000, "limit": 10_000_000_000,
         "unit": "bytes", "period": "now", "percent": 82.0, "level": "80", "source": "cloudflare",
         "self": 8_100_000_000, "cloudflare": 8_200_000_000, "cloudflare_at": "2026-10-23T08:47:00.000Z",
         "costs_money": True},
    ]
    w = [{"id": "r2_speicher", "name": "R2 storage", "level": "80", "percent": 82.0,
          "text": "R2 storage at 82 % (8.20 GB of 10.00 GB)."},
         {"id": "worker_anfragen", "name": "Worker requests", "level": "50", "percent": 60.0,
          "text": "Worker requests at 60 % (60,000 of 100,000)."}]
    return {"zeit": "2026-10-23T09:12:00.000Z", "grenzen_geprueft": "2026-10-23",
            "grenzen": g, "warnungen": w if stufen != ("ok",) else []}


def _nutzung_aufrufe(geraet):
    return [a for a in geraet.zustand.aufrufe if a == ("GET", "/v1/nutzung")]


@pytest.fixture
def betreiber(geraet):
    konto.anlegen(konto.Entwurf(PW), "s@x.org", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    geraet.zustand.betreiber.add("s@x.org")
    geraet.zustand.nutzung = _bericht()
    return geraet


def test_cloud_usage_balken_zeitraum_quelle(betreiber):
    term = Spiel()
    assert haupt.main(["cloud", "usage"], term=term) == 0
    txt = term.text
    assert "Cloud usage" in txt and "2026-10-23 09:12 UTC" in txt
    assert "Worker requests" in txt and " 60.0 %" in txt and "60,000 / 100,000 requests" in txt
    assert "today (UTC)" in txt and "self-counted" in txt
    assert "8.20 GB / 10.00 GB" in txt and "right now" in txt
    assert "Cloudflare 8.20 GB (08:47)" in txt and "self-counted 8.10 GB" in txt
    zeile = next(z for z in txt.splitlines() if z.strip().startswith("R2 storage") and "%" in z)
    assert zeile.count("█") == round(0.82 * 24) and zeile.count("░") == 24 - round(0.82 * 24)
    assert "R2 storage at 82 %" in txt and "Only R2 costs money" in txt
    assert "\x1b[" not in txt                                        # kein Terminal → keine Farbe


def test_cloud_usage_farbe_nach_stufe(betreiber):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    term = Terminal(aus=Tty(), ein=io.StringIO())
    term.farbig = True
    assert befehle.cloud_usage(term) == 0
    txt = term.aus.getvalue()
    assert "\x1b[33;1m" in txt and "\x1b[33m" in txt                 # 80 % gelb fett, 50 % gelb


def test_cloud_usage_nicht_betreiber_hoeflich(geraet):
    konto.anlegen(konto.Entwurf(PW), "s@x.org", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    term = Spiel()
    assert haupt.main(["cloud", "usage"], term=term) == 1
    assert "only for the operator" in term.text and "Error" not in term.text
    # Danach fragt die Warnzeile einen Tag lang nicht mehr nach.
    vorher = len(_nutzung_aufrufe(geraet))
    term = Spiel()
    assert befehle.status(term) == 0
    assert "Cloud free tier" not in term.text
    assert len(_nutzung_aufrufe(geraet)) == vorher


def test_cloud_usage_nicht_angemeldet(geraet):
    term = Spiel()
    assert haupt.main(["cloud", "usage"], term=term) == 1
    assert "Not logged in" in term.text and not _nutzung_aufrufe(geraet)


def test_warnzeile_genau_eine_und_eine_stunde_gemerkt(betreiber, monkeypatch):
    import cloud_nutzung
    term = Spiel()
    assert befehle.status(term) == 0
    zeilen = [z for z in term.text.splitlines() if "Cloud free tier" in z]
    assert zeilen == ["Cloud free tier: R2 storage at 82 % (8.20 GB of 10.00 GB) (+1 more). "
                      "See 'zentrale cloud usage'."]
    assert len(_nutzung_aufrufe(betreiber)) == 1
    # Innerhalb einer Stunde: aus dem Cache, kein Netz.
    term = Spiel()
    befehle.status(term)
    assert "Cloud free tier" in term.text and len(_nutzung_aufrufe(betreiber)) == 1
    # Nach mehr als einer Stunde: neu gefragt — jetzt ohne Warnung.
    betreiber.zustand.nutzung = _bericht("ok")
    import time as _time
    echt = _time.time
    monkeypatch.setattr(cloud_nutzung.time, "time", lambda: echt() + cloud_nutzung.GUELTIG_S + 5)
    term = Spiel()
    befehle.status(term)
    assert "Cloud free tier" not in term.text and len(_nutzung_aufrufe(betreiber)) == 2


def test_start_zeigt_warnzeile_vor_der_tui(betreiber, monkeypatch):
    gestartet = []
    monkeypatch.setattr(befehle, "tui", lambda term: gestartet.append(term.text) or 0)
    monkeypatch.setattr(haupt, "_entwickler_checkout", lambda: True)
    term = Spiel()
    assert haupt.main([], term=term) == 0
    assert gestartet and gestartet[0].count("Cloud free tier") == 1


def test_start_offline_schnell_ohne_fehler_und_gemerkt(betreiber, monkeypatch):
    import time as _time

    import cloud_nutzung
    betreiber.stopp()                                                # Cloud weg
    gestartet = []
    monkeypatch.setattr(befehle, "tui", lambda term: gestartet.append(1) or 0)
    monkeypatch.setattr(haupt, "_entwickler_checkout", lambda: True)
    term = Spiel()
    t0 = _time.monotonic()
    assert haupt.main([], term=term) == 0
    assert _time.monotonic() - t0 < cloud_nutzung.ZEIT_START + 1
    assert gestartet == [1] and "Cloud free tier" not in term.text and "Error" not in term.text
    # Der Fehlschlag gilt eine Stunde: der nächste Start fragt gar nicht erst.
    monkeypatch.setattr(cloud_nutzung, "holen", lambda *a, **k: pytest.fail("nicht fragen"))
    assert haupt.main([], term=Spiel()) == 0 and gestartet == [1, 1]


def test_warnung_wirft_nie(betreiber, monkeypatch):
    import cloud_nutzung
    monkeypatch.setattr(cloud_nutzung, "holen", lambda *a, **k: 1 / 0)
    assert cloud_nutzung.warnung() is None
    with open(cloud_nutzung._pfad(), "w", encoding="utf-8") as f:
        f.write("{kaputt")
    assert cloud_nutzung.warnung() is None
