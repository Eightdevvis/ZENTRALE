"""Hub-Grundlagen (2026-10-22, memory/hub/kern_auszug_inventur.md D Schritt 1,
memory/hub/hub_bauplan.md „Apps starten, stoppen, weiterreichen"):

  GET  /api/apps, POST /api/apps/<name>/start|stop  (core/app_verwaltung.py)
  Weiterleitung `routen` im app.toml                  (core/app_weiterleitung.py)
  Kachel-Quelle über HTTP                             (core/kachel_http.py)

Geprüft gegen echte kleine HTTP-Server (im Thread oder als eigener Prozess),
nicht gegen Attrappen der Leitung — genau das Zusammenspiel ist die Stelle,
an der eine Weiterleitung kaputtgeht.
"""
import json
import os
import socket
import sys
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import app_verwaltung
import app_weiterleitung
import apps
import kachel_fokus
import kacheln
import lists
from kachel_form import KachelFehler, KachelWeg, KachelZuKlein


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture(autouse=True)
def _tabelle_frisch():
    app_weiterleitung.vergessen()
    yield
    app_weiterleitung.vergessen()


def _app_einhaengen(monkeypatch, tmp_path, name, toml):
    """Eine Prozess-App `name` mit diesem app.toml installieren (nur im Test)."""
    ordner = tmp_path / ("app_" + name)
    ordner.mkdir()
    (ordner / "app.toml").write_text(toml, encoding="utf-8")
    monkeypatch.setitem(apps.BEKANNT, name, "gibt-es-nicht-" + name)
    monkeypatch.setenv("ZENTRALE_APP_PFAD_" + name.upper(), str(ordner))
    app_weiterleitung.vergessen()
    return ordner


def _server(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Weiterleitung ─────────────────────────────────────────────────────

class _Probe(BaseHTTPRequestHandler):
    """Antwortet mit allem, was sie gesehen hat — so sieht der Test, was
    durchging."""
    gesehen = []
    langsam = 0.0

    def _antwort(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        _Probe.gesehen.append({"methode": self.command, "pfad": self.path, "body": body,
                               "koepfe": {k.lower(): v for k, v in self.headers.items()}})
        if _Probe.langsam:
            time.sleep(_Probe.langsam)
        if self.path.startswith("/api/probe/umleitung"):
            self.send_response(302)
            self.send_header("Location", "/api/probe/ziel")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        status = 418 if self.path.startswith("/api/probe/teekanne") else 200
        roh = b'{"a": 1,  "b":"\xc3\xa4"}\n' if status == 200 else b"kein kaffee"
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if status == 200 else "text/plain")
        self.send_header("ETag", '"v1"')
        self.send_header("Set-Cookie", "app=geheim")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _antwort

    def log_message(self, *a):
        pass


@pytest.fixture
def probe(monkeypatch, tmp_path):
    srv = _server(_Probe)
    _Probe.gesehen, _Probe.langsam = [], 0.0
    _app_einhaengen(monkeypatch, tmp_path, "probe",
                    'name = "probe"\nversion = "1.2.3"\nstart = "python -m probe"\n'
                    'adresse = "http://127.0.0.1:%d"\nrouten = ["/api/probe"]\n' % srv.server_port)
    yield srv
    srv.shutdown()


def test_get_mit_abfrage_geht_unveraendert_durch(client, probe):
    r = client.get("/api/probe/x/y?b=2&a=%C3%A4&a=1", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.data == b'{"a": 1,  "b":"\xc3\xa4"}\n', "körper byte-gleich, nicht neu als JSON gebaut"
    assert r.headers["Content-Type"] == "application/json" and r.headers["ETag"] == '"v1"'
    g = _Probe.gesehen[-1]
    assert g["methode"] == "GET" and g["pfad"] == "/api/probe/x/y?b=2&a=%C3%A4&a=1"
    assert g["koepfe"]["accept"] == "application/json"


def test_post_koerper_und_status_gehen_durch(client, probe):
    roh = b'{"liste": "l_x", "n": 3}'
    r = client.post("/api/probe/teekanne", data=roh, content_type="application/json")
    assert r.status_code == 418 and r.data == b"kein kaffee"
    assert r.headers["Content-Type"] == "text/plain"
    g = _Probe.gesehen[-1]
    assert g["methode"] == "POST" and g["body"] == roh
    assert g["koepfe"]["content-type"] == "application/json"
    for methode in ("put", "delete", "patch"):
        assert getattr(client, methode)("/api/probe").status_code == 200
    assert [g["methode"] for g in _Probe.gesehen[-3:]] == ["PUT", "DELETE", "PATCH"]


def test_schluessel_und_kekse_bleiben_beim_hub(client, probe):
    client.get("/api/probe", headers={"Authorization": "Bearer hub-geheim",
                                      "Cookie": "zentrale_zugang=x"})
    koepfe = _Probe.gesehen[-1]["koepfe"]
    assert "authorization" not in koepfe and "cookie" not in koepfe
    r = client.get("/api/probe")
    assert "Set-Cookie" not in r.headers, "die App setzt keine Kekse für den Hub"


def test_umleitung_der_app_geht_an_den_aufrufer(client, probe):
    r = client.get("/api/probe/umleitung")
    assert r.status_code == 302 and r.headers["Location"].endswith("/api/probe/ziel")
    assert len(_Probe.gesehen) == 1, "der Hub folgt nicht selbst"


def test_praefix_nur_an_abschnittsgrenzen(client, probe):
    assert app_weiterleitung.besitzer("/api/probex") is None
    assert client.get("/api/probex").status_code == 404
    assert app_weiterleitung.besitzer("/api/probe")["name"] == "probe"
    assert app_weiterleitung.besitzer("/api/state") is None


def test_app_aus_ist_503_aus(client, monkeypatch, tmp_path):
    _app_einhaengen(monkeypatch, tmp_path, "probe",
                    'name = "probe"\nstart = "python -m probe"\n'
                    'adresse = "http://127.0.0.1:%d"\nrouten = ["/api/probe"]\n' % _freier_port())
    r = client.get("/api/probe/x")
    assert r.status_code == 503 and r.get_json()["fehler"] == "aus"


def test_langsame_app_ist_503_aus(client, probe, monkeypatch):
    monkeypatch.setattr(app_weiterleitung, "WARTEZEIT", 0.2)
    _Probe.langsam = 0.6
    t0 = time.monotonic()
    r = client.get("/api/probe/x")
    assert r.status_code == 503 and r.get_json()["fehler"] == "aus"
    assert time.monotonic() - t0 < 2


def test_tuer_des_hubs_gilt_auch_fuer_apps(client, probe, monkeypatch):
    """Die Weiterleitung kommt NACH der Zugangsprüfung."""
    import zugang
    monkeypatch.setattr(zugang, "modus", lambda: "an")
    r = client.get("/api/probe/x", environ_base={"REMOTE_ADDR": "192.168.1.50"},
                   headers={"Host": "192.168.1.2:5000"})
    assert r.status_code == 401 and _Probe.gesehen == []


def test_vorlage_apps_und_kaputte_routen_leiten_nicht(monkeypatch, tmp_path):
    _app_einhaengen(monkeypatch, tmp_path, "probe",
                    'name = "probe"\nrouten = ["/api/probe"]\n')        # ohne start/adresse
    assert app_weiterleitung.besitzer("/api/probe") is None
    m = {"start": "x", "adresse": "http://h", "routen": ["api/ohne", "/", "/a/../b", "/ok/"]}
    assert apps.routen(m) == ["/ok"]


# ── /api/apps, Start und Stopp ────────────────────────────────────────

_SERVER = textwrap.dedent('''
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            roh = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)
        def log_message(self, *a):
            pass

    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
''')


@pytest.fixture
def prozess_app(monkeypatch, tmp_path):
    port = _freier_port()
    ordner = _app_einhaengen(
        monkeypatch, tmp_path, "probe",
        'name = "probe"\ntitel = "Probe"\nversion = "0.1.0"\nstart = "python server.py %d"\n'
        'adresse = "http://127.0.0.1:%d"\nansichten = ["terminal"]\nautostart = true\n'
        'routen = ["/api/probe"]\nliefert = []\n' % (port, port))
    (ordner / "server.py").write_text(_SERVER, encoding="utf-8")
    monkeypatch.setattr(app_verwaltung, "_eigene", {})
    yield ordner
    app_verwaltung.eigene_stoppen()


def test_api_apps_listet_aus_den_manifesten(client, prozess_app):
    r = client.get("/api/apps")
    assert r.status_code == 200
    nach_name = {a["name"]: a for a in r.get_json()}
    p = nach_name["probe"]
    assert p == {"name": "probe", "titel": "Probe", "version": "0.1.0", "art": "prozess",
                 "adresse": p["adresse"], "laeuft": False, "gestartet_vom_hub": False,
                 "autostart": True, "ansichten": ["terminal"], "rechte": [], "liefert": [],
                 "routen": ["/api/probe"], "daten": None, "quelle": None, "icon": None,
                 "ansichten_installiert": [{"id": "terminal", "titel": "im terminal",
                                            "start": False}]}
    assert nach_name["tutor"]["laeuft"] is False       # Test-App zeigt ins Leere


def test_start_stopp_nur_eigenes(client, prozess_app):
    r = client.post("/api/apps/probe/start")
    assert r.status_code == 200 and r.get_json() == {"name": "probe", "laeuft": True,
                                                      "gestartet": True}
    eintrag = {a["name"]: a for a in client.get("/api/apps").get_json()}["probe"]
    assert eintrag["laeuft"] and eintrag["gestartet_vom_hub"]
    assert os.path.exists(os.path.join(app_verwaltung.lauf_ordner(), "probe.pid"))
    # zweimal starten startet nicht doppelt
    assert client.post("/api/apps/probe/start").get_json()["gestartet"] is False
    proc = app_verwaltung._eigene["probe"][0]
    r = client.post("/api/apps/probe/stop")
    assert r.status_code == 200 and r.get_json() == {"name": "probe", "gestoppt": True}
    assert proc.poll() is not None
    assert not os.path.exists(os.path.join(app_verwaltung.lauf_ordner(), "probe.pid"))
    # einmal gestoppt: nicht mehr eigen
    assert client.post("/api/apps/probe/stop").status_code == 409


def test_fremd_gestartete_app_bleibt_in_ruhe(client, prozess_app):
    import subprocess
    port = int(apps.manifest("probe")["adresse"].rsplit(":", 1)[1])
    fremd = subprocess.Popen([sys.executable, str(prozess_app / "server.py"), str(port)])
    try:
        for _ in range(40):
            if app_verwaltung.app_prozess.lebt(apps.manifest("probe")["adresse"], 0.2):
                break
            time.sleep(0.05)
        assert client.post("/api/apps/probe/start").get_json() == {
            "name": "probe", "laeuft": True, "gestartet": False}
        r = client.post("/api/apps/probe/stop")
        assert r.status_code == 409 and r.get_json()["fehler"] == "fremd"
        assert fremd.poll() is None
    finally:
        fremd.terminate()
        fremd.wait(5)


def test_nach_hot_reload_erkennt_der_hub_seine_app(prozess_app):
    assert app_verwaltung.starten("probe")["gestartet"]
    proc = app_verwaltung._eigene["probe"][0]
    app_verwaltung._eigene.clear()                # wie nach os.execv: Speicher leer
    assert app_verwaltung.gestartet_vom_hub("probe")
    assert app_verwaltung.stoppen("probe")["gestoppt"]
    proc.wait(5)


def test_fehler_beim_start(client, monkeypatch, tmp_path, prozess_app):
    assert client.post("/api/apps/gibtsnicht/start").status_code == 404
    assert client.post("/api/apps/..%2F..%2Fetc/start").status_code == 404
    (prozess_app / "server.py").write_text("raise SystemExit(3)\n")
    r = client.post("/api/apps/probe/start")
    assert r.status_code == 503 and r.get_json()["fehler"] == "aus"


def test_vorlage_app_ist_kein_prozess(client, monkeypatch, tmp_path):
    _app_einhaengen(monkeypatch, tmp_path, "geige", 'name = "Geige"\nvorlage = "desk"\n')
    r = client.post("/api/apps/geige/start")
    assert r.status_code == 400 and r.get_json()["fehler"] == "kein_prozess"
    eintrag = {a["name"]: a for a in client.get("/api/apps").get_json()}
    assert eintrag["Geige"]["art"] == "vorlage" and eintrag["Geige"]["laeuft"] is None


def test_autostart(prozess_app, monkeypatch):
    monkeypatch.setenv("ZENTRALE_APPS_AUTOSTART", "aus")
    assert app_verwaltung.autostart() == []
    monkeypatch.setenv("ZENTRALE_APPS_AUTOSTART", "an")
    assert app_verwaltung.autostart() == ["probe"]
    assert app_verwaltung.eigene_stoppen() == ["probe"]


def test_lebt_fragt_nicht_ueber_einen_proxy(probe, monkeypatch):
    """Ein gesetzter http_proxy darf die Frage an die lokale App nicht
    umlenken (sonst „lebt nicht", obwohl sie läuft)."""
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    assert app_verwaltung.app_prozess.lebt("http://127.0.0.1:%d" % probe.server_port)


def test_starter_und_hub_teilen_die_handgriffe():
    """Kein dritter Satz Start-Code: open_tutor_room und apps nehmen
    core/app_prozess.py."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for datei in ("scripts/open_tutor_room.py", "core/apps.py", "core/app_verwaltung.py"):
        with open(os.path.join(root, datei), encoding="utf-8") as f:
            quelle = f.read()
        assert "app_prozess" in quelle, datei
        assert "subprocess.Popen(_befehl" not in quelle and "/hub/gesund\", timeout" not in quelle


# ── Kachel-Quelle über HTTP ───────────────────────────────────────────

def _quelle_als_server(modul):
    """Eine Quelle im Prozess als App hinter HTTP — das Protokoll aus
    core/kachel_http.py, so wie eine ausgezogene App es beantwortet."""

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            a = json.loads(self.rfile.read(n))
            try:
                if self.path == "/hub/kachel":
                    status, antwort = 200, modul.kachel(a["art"], a["ref"], a["w"], a["h"], a["oben"])
                elif self.path == "/hub/kachel/aktion":
                    status, antwort = 200, modul.aktion(a["art"], a["ref"], a["aktion"])
                elif self.path == "/hub/kachel/parameter":
                    status, antwort = 200, {"schema": modul.parameter_jetzt(a["art"], a["schema"])}
                elif self.path == "/hub/kachel/bevorzugt":
                    w, h = modul.bevorzugt(a["art"], a["ref"])
                    status, antwort = 200, {"w": w, "h": h}
                else:
                    status, antwort = 404, {"fehler": "unbekannt"}
            except KachelZuKlein as e:
                status, antwort = 200, {"zu_klein": {"w": e.w, "h": e.h}}
            except KachelWeg:
                status, antwort = 404, {"fehler": "weg"}
            except KachelFehler as e:
                status, antwort = 400, {"fehler": "ungueltig", "text": str(e)}
            roh = json.dumps(antwort).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

        def log_message(self, *a):
            pass
    return _server(H)


def _manifest_aus(modul, port):
    """[kachel.<art>] aus den ARTEN der Quelle (Schema als Datei daneben)."""
    zeilen = ['name = "%s"' % modul.APP, 'start = "python -m x"',
              'adresse = "http://127.0.0.1:%d"' % port,
              "liefert = [%s]" % ", ".join('"kachel:%s"' % a for a in modul.ARTEN)]
    schemas = {}
    for art, info in modul.ARTEN.items():
        zeilen.append("[kachel.%s]" % art)
        for k in ("titel", "ttl"):
            zeilen.append("%s = %s" % (k, json.dumps(info[k])))
        for k in ("min", "bevorzugt", "max"):
            if k in info:
                zeilen.append("%s = %s" % (k, json.dumps(list(info[k]))))
        zeilen.append('parameter = "schema_%s.json"' % art)
        zeilen.append('kann = ["aktion", "parameter_jetzt", "bevorzugt"]')
        schemas["schema_%s.json" % art] = info["parameter"]
    return "\n".join(zeilen) + "\n", schemas


@pytest.fixture
def liste():
    lid = lists.create_list("Einkauf")["id"]
    for t in ("Milch", "Brot", "Käse", "Äpfel"):
        lists.add_item(lid, t)
    return lid


def _antworten(lid):
    """Alles, was eine Oberfläche den Hub zu Listen-Kacheln fragen kann."""
    adresse = "zentrale://fokus/liste?erledigte=false&liste=%s" % lid
    raus = {"katalog": kacheln.katalog()}
    for name, anfrage in {
        "normal": {"adresse": adresse, "w": 40, "h": 12},
        "geblaettert": {"adresse": adresse, "w": 40, "h": 9, "oben": 1},
        "zu_klein": {"adresse": adresse, "w": 3, "h": 3},
        "weg": {"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_weg", "w": 40, "h": 9},
        "ungueltig": {"adresse": "zentrale://fokus/liste?erledigte=vielleicht&liste=x", "w": 9, "h": 9},
    }.items():
        raus[name] = kacheln.holen(anfrage)
    stand = raus["normal"][1]["stand"]
    raus["unveraendert"] = kacheln.holen({"adresse": adresse, "w": 40, "h": 12, "stand": stand})
    raus["aktion"] = kacheln.aktion({"adresse": adresse, "aktion": "oeffnen"})
    raus["aktion_weg"] = kacheln.aktion({"adresse": "zentrale://fokus/liste?erledigte=false&liste=l_weg",
                                         "aktion": "oeffnen"})
    return raus


def test_kachel_ueber_http_gleich_wie_im_prozess(monkeypatch, tmp_path, liste):
    im_prozess = _antworten(liste)
    srv = _quelle_als_server(kachel_fokus)
    try:
        toml, schemas = _manifest_aus(kachel_fokus, srv.server_port)
        ordner = _app_einhaengen(monkeypatch, tmp_path, "fokus", toml)
        for datei, schema in schemas.items():
            (ordner / datei).write_text(json.dumps(schema), encoding="utf-8")
        monkeypatch.delitem(kacheln.QUELLEN, "fokus")   # die App liefert, nicht der Kern
        assert type(kacheln._quellen()["fokus"]).__name__ == "Quelle"
        ueber_http = _antworten(liste)
    finally:
        srv.shutdown()
    for k in im_prozess:
        assert json.dumps(ueber_http[k], sort_keys=True, ensure_ascii=False) == \
            json.dumps(im_prozess[k], sort_keys=True, ensure_ascii=False), k


def test_app_gewinnt_gegen_quelle_im_prozess(monkeypatch, tmp_path, liste):
    """Heißt die App wie eine eingebaute Quelle, fragt der Hub die App."""
    toml, schemas = _manifest_aus(kachel_fokus, _freier_port())
    ordner = _app_einhaengen(monkeypatch, tmp_path, "fokus", toml)
    for datei, schema in schemas.items():
        (ordner / datei).write_text(json.dumps(schema), encoding="utf-8")
    status, antwort = kacheln.holen({"adresse": "zentrale://fokus/liste?erledigte=false&liste=%s"
                                     % liste, "w": 40, "h": 9})
    assert status == 503 and antwort["fehler"] == "aus"      # App aus → „aus", kein Rückfall


def test_langsame_kachel_app_ist_aus(monkeypatch, tmp_path, liste):
    class Langsam(BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(1.0)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = _server(Langsam)
    try:
        toml, schemas = _manifest_aus(kachel_fokus, srv.server_port)
        toml = toml.replace('kann = ["aktion", "parameter_jetzt", "bevorzugt"]', "kann = []")
        ordner = _app_einhaengen(monkeypatch, tmp_path, "fokus", toml)
        for datei, schema in schemas.items():
            (ordner / datei).write_text(json.dumps(schema), encoding="utf-8")
        t0 = time.monotonic()
        status, antwort = kacheln.holen({"adresse": "zentrale://fokus/liste?erledigte=false&liste=%s"
                                         % liste, "w": 40, "h": 9})
        assert status == 503 and antwort["fehler"] == "aus"
        assert time.monotonic() - t0 < 0.9, "Zeitbudget 0,5 s"
    finally:
        srv.shutdown()


def test_schema_datei_ausserhalb_der_app_zaehlt_nicht(monkeypatch, tmp_path):
    _app_einhaengen(monkeypatch, tmp_path, "probe",
                    'name = "probe"\nstart = "x"\nadresse = "http://127.0.0.1:9"\n'
                    'liefert = ["kachel:k"]\n[kachel.k]\ntitel = "k"\nparameter = "../../etc/passwd"\n')
    assert "probe" not in kacheln._quellen()
