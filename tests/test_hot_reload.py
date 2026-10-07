"""Hot Reload fürs Backend (core/hot_reload.py): wann der Wächter neu startet."""
import os
import time

import hot_reload


def _waechter(tmp_path, logs):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "a.py").write_text("x = 1\n")
    (tmp_path / "core" / "test_a.py").write_text("y = 1\n")
    dateien = lambda: hot_reload.code_dateien(str(tmp_path), ("core",))
    return hot_reload.Waechter(logs.append, dateien=dateien, alle=1)


def _aendern(pfad, text):
    pfad.write_text(text)
    st = os.stat(pfad)
    os.utime(pfad, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))


frei = lambda: None


def test_tests_und_pycache_zaehlen_nicht(tmp_path):
    (tmp_path / "core" / "__pycache__").mkdir(parents=True)
    (tmp_path / "core" / "__pycache__" / "a.py").write_text("")
    (tmp_path / "core" / "test_x.py").write_text("")
    (tmp_path / "core" / "b.py").write_text("")
    namen = [os.path.basename(p) for p in hot_reload.code_dateien(str(tmp_path), ("core",))]
    assert namen == ["b.py"]


def test_ohne_aenderung_kein_neustart(tmp_path):
    w = _waechter(tmp_path, [])
    assert not any(w.tick(frei) for _ in range(5))


def test_neustart_erst_wenn_code_ruht(tmp_path):
    w = _waechter(tmp_path, [])
    _aendern(tmp_path / "core" / "a.py", "x = 2\n")
    assert w.tick(frei) is False        # gerade geändert — Kandidat merken
    assert w.tick(frei) is True         # eine Prüfung später unverändert


def test_wartet_solange_beschaeftigt(tmp_path):
    logs = []
    w = _waechter(tmp_path, logs)
    _aendern(tmp_path / "core" / "a.py", "x = 2\n")
    w.tick(frei)
    assert w.tick(lambda: "1 laufende(r) Request(s)") is False
    assert w.tick(lambda: "1 laufende(r) Request(s)") is False
    assert sum("wartet" in l for l in logs) == 1     # nur einmal melden
    assert w.tick(frei) is True


def test_kaputter_code_bleibt_beim_alten(tmp_path):
    logs = []
    w = _waechter(tmp_path, logs)
    _aendern(tmp_path / "core" / "a.py", "def (:\n")
    w.tick(frei)
    assert w.tick(frei) is False
    assert any("kaputt" in l and "a.py" in l for l in logs)
    assert w.tick(frei) is False        # dieselbe kaputte Fassung nicht nochmal
    _aendern(tmp_path / "core" / "a.py", "x = 3\n")
    w.tick(frei)
    assert w.tick(frei) is True         # repariert → jetzt geht's


def test_abschaltbar(monkeypatch):
    monkeypatch.setenv("ZENTRALE_HOT_RELOAD", "aus")
    assert hot_reload.an() is False
    monkeypatch.setenv("ZENTRALE_HOT_RELOAD", "")
    assert hot_reload.an() is True


def test_request_zaehlt_bis_stream_ende():
    from flask import Flask, Response
    app = Flask("probe")
    hot_reload.requests_zaehlen(app)
    gesehen = []

    @app.route("/stream")
    def stream():
        def gen():
            gesehen.append(hot_reload.laufende_requests())
            yield "a"
            gesehen.append(hot_reload.laufende_requests())
            yield "b"
        return Response(gen(), content_type="text/event-stream")

    @app.route("/api/ai/debug/stream")
    def debug():
        gesehen.append(hot_reload.laufende_requests())
        return "x"

    c = app.test_client()
    vorher = hot_reload.laufende_requests()
    r = c.get("/stream", buffered=False)
    assert b"".join(r.response) == b"ab"
    assert gesehen == [vorher + 1, vorher + 1]   # mitten im Stream: läuft
    r.close()
    assert hot_reload.laufende_requests() == vorher
    c.get("/api/ai/debug/stream")
    assert gesehen[-1] == vorher                  # Debug-Stream zählt nicht


# ── Zählen bis ganz zum Ende — egal wie die Anfrage endet (2026-10-07) ───
#
# Anlass: Journal 07.10. ab 23:26 nur noch „wartet: 1 laufende(r)
# Request(s)", nie 0 — eine Anfrage blieb für immer gezählt. Diese Tests
# stellen die Wege nach, auf denen das alte before/after_request-Zählen
# hängen blieb.

import io
import socket
import threading

import pytest
from flask import Flask, Response, send_file


@pytest.fixture
def leer(monkeypatch):
    """Eigenes, leeres Register — andere Tests lassen Antworten offen."""
    monkeypatch.setattr(hot_reload, "_anfragen", {})
    monkeypatch.setattr(hot_reload, "_ignoriert_gemeldet", set())


def _app():
    app = Flask("probe")
    hot_reload.requests_zaehlen(app)
    app.ende = []

    @app.route("/ok")
    def ok():
        return "ok"

    @app.route("/datei")
    def datei():
        return send_file(io.BytesIO(b"abc"), mimetype="text/plain")

    @app.route("/fehler")
    def fehler():
        raise RuntimeError("route")

    @app.route("/strom")
    def strom():
        def gen():
            try:
                for i in range(5):
                    yield f"data: {i}\n\n"
            finally:
                app.ende.append("strom")
        return Response(gen(), content_type="text/event-stream")

    @app.route("/strom_fehler")
    def strom_fehler():
        def gen():
            yield "a"
            raise RuntimeError("generator")
        return Response(gen())
    return app


def _holen(app, pfad):
    try:
        app.test_client().get(pfad).close()
    except RuntimeError:
        pass                    # teardown-/Generator-Fehler schlägt bis zum Client durch


@pytest.mark.parametrize("pfad", ["/ok", "/datei", "/fehler", "/strom",
                                  "/strom_fehler", "/gibts_nicht"])
def test_jede_antwort_zaehlt_wieder_herunter(leer, pfad):
    # /datei: send_file gibt werkzeug ohne ClosingIterator heraus — das alte
    # call_on_close feuerte da nie.
    _holen(_app(), pfad)
    assert hot_reload.laufende_requests() == 0


def test_kaputtes_after_request_haelt_nicht_fest(leer):
    app = _app()

    @app.after_request
    def kaputt(r):
        raise RuntimeError("after")
    _holen(app, "/ok")
    assert hot_reload.laufende_requests() == 0


def test_kaputtes_teardown_haelt_nicht_fest(leer):
    app = _app()

    @app.teardown_request
    def kaputt(e):
        raise RuntimeError("teardown")
    _holen(app, "/ok")
    assert hot_reload.laufende_requests() == 0


def test_abgebrochener_strom_zaehlt_genau_einmal_herunter(leer):
    app = _app()
    c = app.test_client()
    anderer = hot_reload._rein("/api/chat")         # läuft parallel weiter
    r = c.get("/strom", buffered=False)
    next(iter(r.response))                          # ein Stück, dann weg
    assert hot_reload.laufende_requests() == 2
    r.close()
    r.close()                                       # doppelt schließen schadet nicht
    assert hot_reload.laufende_requests() == 1      # der andere zählt noch
    assert app.ende == ["strom"]                    # Generator sauber beendet
    hot_reload._raus(anderer)


def test_echter_server_client_bricht_strom_ab(leer):
    app = Flask("probe")
    hot_reload.requests_zaehlen(app)
    weiter = threading.Event()

    @app.route("/strom")
    def strom():
        def gen():
            yield "data: 1\n\n"
            weiter.wait(5)
            for _ in range(50):         # erst der Schreibversuch merkt den Abbruch
                yield "data: x\n\n"
                time.sleep(0.01)
        return Response(gen(), content_type="text/event-stream")

    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        s = socket.create_connection(("127.0.0.1", srv.server_port))
        s.sendall(b"GET /strom HTTP/1.1\r\nHost: x\r\n\r\n")
        s.recv(100)
        assert hot_reload.laufende_requests() == 1
        s.close()
        weiter.set()
        for _ in range(100):
            if hot_reload.laufende_requests() == 0:
                break
            time.sleep(0.02)
        assert hot_reload.laufende_requests() == 0
    finally:
        srv.shutdown()
        srv.server_close()


# ── Wer blockiert, und wann eine Anfrage als hängend gilt ───────────────

def test_meldung_nennt_pfad_und_alter(leer):
    hot_reload._rein("/api/chat", jetzt=1000.0)
    assert hot_reload.beschaeftigt(jetzt=1000.0 + 185) == "/api/chat seit 3 min"


def test_haengende_anfrage_blockiert_nicht_mehr(leer):
    logs = []
    hot_reload._rein("/api/lists", jetzt=0.0)
    grenze = hot_reload.STILL_GRENZE_S
    assert hot_reload.beschaeftigt(logs.append, jetzt=grenze - 1)
    assert hot_reload.beschaeftigt(logs.append, jetzt=grenze + 60) is None
    assert hot_reload.beschaeftigt(logs.append, jetzt=grenze + 120) is None
    assert len(logs) == 1                               # nur einmal melden
    assert "ignoriere hängende Anfrage /api/lists" in logs[0]


def test_strom_der_sich_regt_haengt_nicht(leer, monkeypatch):
    # Ein langer Strom, der laufend Stücke liefert, ist am Leben — nur
    # Stille zählt, nicht das Alter.
    uhr = [0.0]
    monkeypatch.setattr(hot_reload, "_jetzt", lambda: uhr[0])
    app = _app()
    r = app.test_client().get("/strom", buffered=False)
    teile = iter(r.response)
    next(teile)
    uhr[0] = hot_reload.STILL_GRENZE_S * 3
    next(teile)                                         # regt sich jetzt
    assert hot_reload.beschaeftigt(jetzt=uhr[0] + 1).startswith("/strom seit")
    r.close()


def test_chat_strom_ueberdauert_laengsten_stillen_werkzeuglauf(leer):
    # run_code darf bis sandbox.ZEITLIMIT_MAX_S still laufen; so lange darf
    # ein Chat-Strom nie als hängend gelten (sonst Neustart mitten im Satz).
    import sandbox
    assert hot_reload.STILL_GRENZE_CHAT_S > sandbox.ZEITLIMIT_MAX_S
    hot_reload._rein("/api/chat", jetzt=0.0)
    still = sandbox.ZEITLIMIT_MAX_S + 60
    assert hot_reload.beschaeftigt(jetzt=still) == f"/api/chat seit {still // 60} min"
    assert hot_reload.beschaeftigt(jetzt=hot_reload.STILL_GRENZE_CHAT_S) is None


def test_waechter_startet_trotz_haengender_anfrage(tmp_path, leer, monkeypatch):
    logs = []
    w = _waechter(tmp_path, logs)
    monkeypatch.setattr(hot_reload, "_jetzt", lambda: 10_000.0)
    hot_reload._rein("/api/state", jetzt=10_000.0 - hot_reload.STILL_GRENZE_S - 1)
    _aendern(tmp_path / "core" / "a.py", "x = 2\n")
    w.tick()
    assert w.tick() is True
    assert any("ignoriere hängende Anfrage /api/state" in l for l in logs)
