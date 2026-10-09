"""Zugangsschlüssel des Backends (core/zugang.py, ui/routen/zugang.py,
memory/betrieb/zugang.md, 2026-10-08).

Verhalten: von diesem Rechner frei; von draußen nur mit Schlüssel (Kopf,
Keks aus einem Browser-Link); Modus melden lässt durch und schreibt auf,
Modus aus prüft nichts. Dazu: die Klienten schicken den Schlüssel mit, und
nur an ihr Backend.
"""
import http.server
import importlib.util
import os
import stat
import threading
import urllib.request

import pytest

import ablage
import ai_config
import zugang

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREMD = {"REMOTE_ADDR": "192.168.50.10"}


@pytest.fixture
def schluessel(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ZUGANG_SCHLUESSEL", str(tmp_path / "zugang.schluessel"))
    zugang.anlegen()
    return zugang.laden()


@pytest.fixture
def modus(monkeypatch):
    def setzen(m):
        monkeypatch.setenv("ZENTRALE_ZUGANG", m)
    yield setzen
    # Auch was ein Test „dauerhaft" gesetzt hat, wieder weg (die Datei liegt
    # in Tests ohnehin im Wegwerf-Ordner, conftest).
    ai_config._overrides.pop("zugang", None)
    ai_config._config.pop("zugang", None)


@pytest.fixture
def client():
    from ui.app import app
    from ui.routen import zugang as tuer
    app.config.update(TESTING=True)
    tuer._gemeldet.clear()
    tuer._zuletzt_geloggt.clear()
    return app.test_client()


def _bearer(k):
    return {"Authorization": f"Bearer {k}"}


# ── Schlüssel ──────────────────────────────────────────────────────────

def test_schluessel_liegt_nur_fuer_sasha_lesbar(schluessel):
    assert len(schluessel) >= 40
    assert stat.S_IMODE(os.stat(zugang.pfad()).st_mode) == 0o600


def test_anlegen_ueberschreibt_keinen_vorhandenen(schluessel):
    with pytest.raises(zugang.SchluesselFehler):
        zugang.anlegen()
    assert zugang.laden() == schluessel
    zugang.anlegen(erneuern=True)
    assert zugang.laden() != schluessel          # gilt sofort, ohne Neustart


def test_kaputte_zeile_wird_abgelehnt(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ZUGANG_SCHLUESSEL", str(tmp_path / "z"))
    for falsch in ("", "kurz", "a" * 31, "ä" * 40, "a b" * 20):
        with pytest.raises(zugang.SchluesselFehler):
            zugang.ablegen(falsch)
    (tmp_path / "z").write_text("kaputt")
    assert zugang.laden() is None and not zugang.passt("kaputt")


def test_vergleich(schluessel):
    assert zugang.passt(schluessel)
    assert not zugang.passt(schluessel[:-1] + "x")
    assert not zugang.passt("")
    assert not zugang.passt(None)


def test_unbekannter_modus_zaehlt_als_an(modus):
    modus("vielleicht")
    assert zugang.modus() == "an"
    modus("MELDEN")
    assert zugang.modus() == "melden"


def test_vorgabe_ist_melden():
    assert zugang.modus() == "melden"


def test_link_marke_gilt_zehn_minuten(schluessel):
    m = zugang.link_marke(jetzt=1000)
    assert zugang.link_passt(m, jetzt=1000 + 599)
    assert not zugang.link_passt(m, jetzt=1000 + 601)
    assert not zugang.link_passt(m.replace(".", ".0", 1), jetzt=1000)
    assert not zugang.link_passt("1000.abc", jetzt=1000)
    assert schluessel not in m


# ── Die Tür, Modus an ──────────────────────────────────────────────────

def test_lokal_frei_auch_ohne_schluessel(client, modus):
    modus("an")
    assert client.get("/api/state").status_code == 200


def test_fremd_ohne_schluessel_abgewiesen(client, modus, schluessel):
    modus("an")
    r = client.get("/api/state", environ_base=FREMD)
    assert r.status_code == 401
    assert "Bearer" in r.headers["WWW-Authenticate"]
    assert "Zugangsschlüssel" in r.get_json()["error"]


def test_fremd_mit_falschem_schluessel_abgewiesen(client, modus, schluessel):
    modus("an")
    r = client.get("/api/state", environ_base=FREMD, headers=_bearer("x" * 43))
    assert r.status_code == 401


def test_fremd_mit_schluessel_frei(client, modus, schluessel):
    modus("an")
    assert client.get("/api/state", environ_base=FREMD,
                      headers=_bearer(schluessel)).status_code == 200
    r = client.post("/api/sensor/motion", environ_base=FREMD, headers=_bearer(schluessel))
    assert r.status_code == 200


def test_ohne_schluessel_auf_dem_rechner_kommt_niemand_von_draussen(client, modus):
    modus("an")
    r = client.get("/api/state", environ_base=FREMD, headers=_bearer("y" * 43))
    assert r.status_code == 401


def test_dns_rebinding_gilt_nicht_als_lokal(client, modus, schluessel):
    """127.0.0.1, aber an einen fremden Namen gerichtet: eine Webseite im
    eigenen Browser, die sich als localhost ausgibt."""
    modus("an")
    r = client.get("/api/state", headers={"Host": "boese.example:5000"})
    assert r.status_code == 401


def test_browser_bekommt_eine_seite(client, modus, schluessel):
    modus("an")
    r = client.get("/api/state", environ_base=FREMD, headers={"Accept": "text/html"})
    assert r.status_code == 401 and r.mimetype == "text/html"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_aussenposten_paket_bleibt_frei(client, modus, schluessel):
    """Sonst käme ein Pi ohne Schlüssel nie an die Fassung, die ihn mitschickt."""
    modus("an")
    r = client.get("/api/aussenposten/manifest", environ_base=FREMD)
    assert r.status_code != 401


def test_browser_link_setzt_keks_und_leitet_um(client, modus, schluessel):
    modus("an")
    marke = zugang.link_marke()
    r = client.get(f"/api/state?a=1&zugang={marke}", environ_base=FREMD)
    assert r.status_code == 303
    assert r.headers["Location"].endswith("/api/state?a=1")
    keks = r.headers["Set-Cookie"]
    assert "HttpOnly" in keks and schluessel not in keks
    # Der Test-Client trägt den Keks weiter: ab jetzt frei.
    assert client.get("/api/state", environ_base=FREMD).status_code == 200


def test_abgelaufener_link_hilft_nicht(client, modus, schluessel):
    modus("an")
    alt = zugang.link_marke(jetzt=1)
    assert client.get(f"/api/state?zugang={alt}", environ_base=FREMD).status_code == 401


def test_falscher_keks_hilft_nicht(client, modus, schluessel):
    modus("an")
    client.set_cookie(zugang.KEKS_NAME, "0" * 64)
    assert client.get("/api/state", environ_base=FREMD).status_code == 401


def test_erneuerter_schluessel_macht_alte_kekse_ungueltig(client, modus, schluessel):
    modus("an")
    client.set_cookie(zugang.KEKS_NAME, zugang.keks_wert())
    assert client.get("/api/state", environ_base=FREMD).status_code == 200
    zugang.anlegen(erneuern=True)
    assert client.get("/api/state", environ_base=FREMD).status_code == 401


# ── Hinter der Tür: Morgenblick und Ablage unverändert ─────────────────

def test_ablage_roh_mit_schluessel_behaelt_csp(client, modus, schluessel):
    modus("an")
    k = ablage.anlegen("Seite", "<!doctype html><p>hallo</p>", "html")
    url = f"/api/ablage/{k['id']}/roh"
    assert client.get(url, environ_base=FREMD).status_code == 401
    r = client.get(url, environ_base=FREMD, headers=_bearer(schluessel))
    assert r.status_code == 200
    assert "sandbox" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_morgenblick_knopf_bleibt_nur_lokal_auch_mit_schluessel(client, modus, schluessel):
    import morgenblick as mb
    from datetime import date
    modus("an")
    href = mb.knopf_href(date.today().isoformat(), "Probe", "Etwas tun.")
    r = client.get(href, environ_base=FREMD, headers=_bearer(schluessel))
    assert r.status_code == 403
    assert client.get(href).status_code == 200


# ── Modus melden / aus ─────────────────────────────────────────────────

def test_melden_laesst_durch_und_schreibt_auf(client, modus, schluessel):
    modus("melden")
    assert client.get("/api/state", environ_base=FREMD).status_code == 200
    st = client.get("/api/zugang").get_json()
    assert st["modus"] == "melden" and st["schluessel_da"] is True
    e = st["ohne_schluessel"][-1]
    assert e["von"] == "192.168.50.10" and e["pfad"] == "/api/state" and e["durchgelassen"]


def test_melden_schreibt_das_log_gedrosselt(client, modus, schluessel, monkeypatch):
    import state
    zeilen = []
    monkeypatch.setattr(state, "push_log", zeilen.append)
    modus("melden")
    for _ in range(5):
        client.get("/api/state", environ_base=FREMD)
    assert len([z for z in zeilen if z.startswith("ZUGANG")]) == 1


def test_mit_schluessel_wird_nichts_gemeldet(client, modus, schluessel):
    modus("melden")
    client.get("/api/state", environ_base=FREMD, headers=_bearer(schluessel))
    assert client.get("/api/zugang").get_json()["ohne_schluessel"] == []


def test_aus_prueft_nichts(client, modus, schluessel):
    modus("aus")
    assert client.get("/api/state", environ_base=FREMD,
                      headers=_bearer("falsch" * 8)).status_code == 200
    assert client.get("/api/zugang").get_json()["ohne_schluessel"] == []


def test_steuerung_nur_vom_rechner_selbst(client, modus, schluessel):
    modus("an")
    h = _bearer(schluessel)
    assert client.get("/api/zugang", environ_base=FREMD, headers=h).status_code == 403
    r = client.post("/api/zugang", json={"modus": "aus"}, environ_base=FREMD, headers=h)
    assert r.status_code == 403 and zugang.modus() == "an"


def test_modus_live_umschalten(client, modus):
    assert client.post("/api/zugang", json={"modus": "quatsch"}).status_code == 400
    r = client.post("/api/zugang", json={"modus": "an"})
    assert r.status_code == 200 and r.get_json()["modus"] == "an"
    assert client.get("/api/state", environ_base=FREMD).status_code == 401


# ── Klienten ───────────────────────────────────────────────────────────

class _Merker(http.server.BaseHTTPRequestHandler):
    koepfe = []

    def do_GET(self):
        _Merker.koepfe.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def merker():
    _Merker.koepfe = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Merker)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()
    urllib.request.install_opener(None)


def test_tui_schickt_den_schluessel_nur_an_ihr_backend(merker, schluessel):
    from tui.ansichten import zugang_klient
    zugang_klient.einrichten(merker)
    urllib.request.urlopen(merker + "/api/state").read()
    # Ein anderer Port auf demselben Rechner ist ein anderer Server.
    zugang_klient.einrichten(merker + "1")
    urllib.request.urlopen(merker + "/api/state").read()
    assert _Merker.koepfe == [f"Bearer {schluessel}", None]


def test_tui_ohne_schluessel_schickt_keinen_kopf(merker):
    from tui.ansichten import zugang_klient
    zugang_klient.einrichten(merker)
    urllib.request.urlopen(merker + "/x").read()
    assert _Merker.koepfe == [None]


def _laden(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    return spec, importlib.util.module_from_spec(spec)


def test_alle_klienten_lesen_dieselbe_datei():
    """Die TUI-Umsetzung und die Kopie in der
    Bridge müssen Name und Vorgabe von core/zugang.py behalten."""
    from tui.ansichten import zugang_klient
    assert zugang_klient.VORGABE_PFAD == zugang.VORGABE_PFAD
    assert zugang_klient.ENV == "ZENTRALE_" + "zugang_schluessel".upper()
    for rel in ("scripts/pi_sensor_bridge.py",):
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert f'"{zugang.VORGABE_PFAD}"' in text, rel
        assert '"ZENTRALE_ZUGANG_SCHLUESSEL"' in text, rel
        assert "Bearer" in text, rel


def test_bridge_kopf(schluessel, monkeypatch):
    import sys
    import types
    # Die Bridge braucht requests nur zum Senden; hier geht es um den Kopf.
    monkeypatch.setitem(sys.modules, "requests", sys.modules.get("requests")
                        or types.ModuleType("requests"))
    spec, bridge = _laden("scripts/pi_sensor_bridge.py", "bridge_zugang_test")
    spec.loader.exec_module(bridge)
    assert bridge._zugang_kopf() == {"Authorization": f"Bearer {schluessel}"}


# ── Das Skript ─────────────────────────────────────────────────────────

def _skript():
    spec, mod = _laden("scripts/zugang.py", "zugang_skript_test")
    spec.loader.exec_module(mod)
    mod.LOKAL = "http://127.0.0.1:9"          # kein laufender Kern
    return mod


def test_skript_anlegen_zeigen_link(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ZENTRALE_ZUGANG_SCHLUESSEL", str(tmp_path / "z"))
    s = _skript()
    assert s.main(["zeigen"]) == 1
    assert s.main(["anlegen"]) == 0
    assert s.main(["anlegen"]) == 1               # zweites Mal: weigert sich
    capsys.readouterr()
    assert s.main(["zeigen"]) == 0
    assert capsys.readouterr().out.strip() == zugang.laden()
    assert s.main(["link", "http://pc:5000/api/ablage/x/roh"]) == 0
    link = capsys.readouterr().out.strip()
    assert link.startswith("http://pc:5000/api/ablage/x/roh?zugang=")
    assert zugang.link_passt(link.split("zugang=")[1])


def test_skript_modus_ohne_laufenden_kern(capsys, modus):
    s = _skript()
    assert s.main(["modus", "falsch"]) == 2
    assert s.main(["modus", "an"]) == 0
    assert zugang.modus() == "an"
    assert "nächsten Start" in capsys.readouterr().out


def test_pi_bekommt_was_den_schluessel_mitschickt():
    liste = open(os.path.join(ROOT, "deploy", "aussenposten.txt"), encoding="utf-8").read().split("\n")
    # Das Zimmer der Tutor-App bringt seit 2026-10-09 seinen eigenen
    # Schlüssel-Klienten mit (app:tutor/tutor/zugang.py).
    for noetig in ("app:tutor/tutor/zugang.py", "tui/ansichten/", "scripts/pi_sensor_bridge.py"):
        assert noetig in liste, noetig
