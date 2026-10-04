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
