"""Die Teile um den Abgleich herum: Regeln einzeln, Positivliste, der
Änderungs-Haken in datasync (gedrosselt), der Befehl, die Route.
Der Abgleich selbst (zwei Rechner, eine Mitte): tests/test_abgleich.py."""
import importlib.util
import os

import pytest

import abgleich
import abgleich_auswahl as auswahl
import abgleich_zusammenfuehren as regeln
import ai_config
import datasync

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Regeln ─────────────────────────────────────────────────────────────

def test_nur_eine_seite_geaendert_gilt_ohne_hinweis():
    for b, l, m, soll in ((b"a", b"a", b"b", b"b"), (b"a", b"b", b"a", b"b"),
                          (b"a", None, b"a", None), (b"a", b"a", None, None),
                          (None, b"x", None, b"x"), (None, None, b"x", b"x")):
        r = regeln.zusammenfuehren("data/x.md", b, l, m)
        assert (r.inhalt, r.konflikte) == (soll, [])


def test_zeitstempel_spaeterer_gewinnt_ohne_hinweis():
    b = [{"id": "n", "modified": "2026-10-01", "blocks": [{"id": 1, "text": "a"}]}]
    l = [{"id": "n", "modified": "2026-10-03", "blocks": [{"id": 1, "text": "A"}]}]
    m = [{"id": "n", "modified": "2026-10-02", "blocks": [{"id": 1, "text": "a"},
                                                          {"id": 2, "text": "neu"}]}]
    r, k = regeln.json_zusammenfuehren(b, l, m)
    assert k == []
    assert r[0]["modified"] == "2026-10-03"
    assert [x["text"] for x in r[0]["blocks"]] == ["A", "neu"]


def test_messwerte_ohne_id_als_menge():
    b = [{"date": "1", "value": 1}]
    l = b + [{"date": "2", "value": 5}]
    m = b + [{"date": "3", "value": 7}]
    r, k = regeln.json_zusammenfuehren(b, l, m)
    assert r == [{"date": "1", "value": 1}, {"date": "3", "value": 7}, {"date": "2", "value": 5}]
    assert k == []


def test_kaputtes_json_als_ganzes_mitte_bleibt():
    r = regeln.zusammenfuehren("data/lists.json", b"[]", b"{kaputt", b"[1]")
    assert r.inhalt == b"[1]" and r.konflikte


def test_text_ohne_widerspruch_hat_keine_rahmen():
    t, n = regeln.text_zusammenfuehren("a\nb\nc\n", "x\na\nb\nc\n", "a\nb\nc\ny\n")
    assert (t, n) == ("x\na\nb\nc\ny\n", 0)


# ── Positivliste ───────────────────────────────────────────────────────

@pytest.mark.parametrize("rel,drin", [
    ("data/lists.json", True), ("data/g_gym.json", True),
    ("data/gedaechtnis/dossiers/x.md", True), ("data/gespraeche/g/pc.jsonl", True),
    ("data/kalender_neben.json", True),
    ("data/ai_config.json", False), ("data/mail_secrets.enc", False),
    ("data/kalender/termine/a.ics", False), ("data/ai_calendar.json", False),
    ("data/news_digest.json", False), ("data/_beiseite/a.json", False),
    ("data/gedaechtnis/.sasha.md.123.456.tmp", False),
])
def test_positivliste_abgleich(rel, drin):
    assert auswahl.passt(rel, auswahl.ABGLEICH) is drin


def test_datensicherung_nutzt_dieselbe_liste():
    spec = importlib.util.spec_from_file_location(
        "daten_sichern", os.path.join(ROOT, "scripts", "daten_sichern.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.SICHERN is auswahl.SICHERN
    assert set(auswahl.ABGLEICH) == set(auswahl.SICHERN) - set(auswahl.NICHT_ABGLEICHEN)


# ── Der Haken in datasync ──────────────────────────────────────────────

@pytest.fixture
def haken(monkeypatch):
    gestartet, timer = [], []
    monkeypatch.setenv("ZENTRALE_AUTOPUSH", "1")
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(datasync.subprocess, "Popen", lambda args, **kw: gestartet.append(args))
    monkeypatch.setattr(datasync.shutil, "which", lambda name: "/bin/" + name)

    class FalscherTimer:
        def __init__(self, sek, f):
            self.sek, self.f, self.daemon = sek, f, False
            timer.append(self)

        def start(self):
            pass
    monkeypatch.setattr(datasync.threading, "Timer", FalscherTimer)
    monkeypatch.setattr(datasync, "_drossel", {"zuletzt": float("-inf"), "nachzuegler": None})
    return gestartet, timer


def test_haken_alter_weg_ruft_den_rsync_helfer(haken):
    gestartet, _ = haken
    datasync.notify_change("x")
    assert gestartet == [["/bin/zentrale-push-data"]]


def test_haken_mitte_gedrosselt_und_nichts_vergessen(haken, monkeypatch):
    gestartet, timer = haken
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    for _ in range(5):
        datasync.notify_change("x")
    assert len(gestartet) == 1 and gestartet[0][-2:] == ["jetzt", "--automatisch"]
    assert gestartet[0][1].endswith("scripts/abgleich.py")
    assert len(timer) == 1 and 0 < timer[0].sek <= datasync.DROSSEL   # ein Nachzügler
    timer[0].f()                                  # Fenster vorbei → der Nachzügler läuft
    assert len(gestartet) == 2


def test_haken_ohne_autopush_still(haken, monkeypatch):
    gestartet, _ = haken
    monkeypatch.delenv("ZENTRALE_AUTOPUSH")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    datasync.notify_change("x")
    assert gestartet == []


# ── Befehl und Route ───────────────────────────────────────────────────

def _skript():
    spec = importlib.util.spec_from_file_location(
        "abgleich_skript", os.path.join(ROOT, "scripts", "abgleich.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_befehl_automatisch_ohne_umstellung_tut_nichts(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WURZEL", str(tmp_path))
    monkeypatch.setattr(abgleich, "abgleichen", lambda *a, **k: pytest.fail("darf nicht laufen"))
    assert _skript().main(["jetzt", "--automatisch"]) == 0
    assert capsys.readouterr().out == ""


def test_befehl_status_und_schluessel(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_SCHLUESSEL", str(tmp_path / "k"))
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "z"))
    s = _skript()
    assert s.main(["status"]) == 0
    assert "FEHLT" in capsys.readouterr().out
    assert s.main(["schluessel-zeigen-fuer-keepass"]) == 1
    assert s.main(["schluessel-anlegen"]) == 0
    assert s.main(["schluessel-anlegen"]) == 1          # nie überschreiben
    capsys.readouterr()
    assert s.main(["schluessel-zeigen-fuer-keepass"]) == 0
    aus = capsys.readouterr().out
    assert open(tmp_path / "k").read().strip() in aus and "KeePass" in aus


def test_befehl_ohne_schluessel_klare_meldung(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_SCHLUESSEL", str(tmp_path / "k"))
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "z"))
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WURZEL", str(tmp_path))
    assert _skript().main(["jetzt"]) == 2
    assert "kein Abgleich-Schlüssel" in capsys.readouterr().out


def test_route_zeigt_den_zustand(monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path))
    from ui.app import app
    app.config.update(TESTING=True)
    r = app.test_client().get("/api/abgleich")
    assert r.status_code == 200
    d = r.get_json()
    assert d["weg"] == "rsync" and d["letzter_erfolg"] is None and d["hinweise"] == []


# ── Die Zeile in der TUI (Technik) ─────────────────────────────────────

def test_tui_zeile_abgleich():
    import datetime
    from tui.ansichten.technik import abgleich_zeile
    jetzt = datetime.datetime(2026, 10, 8, 12, 0)
    assert abgleich_zeile(None) is None and abgleich_zeile("müll") is None
    assert abgleich_zeile({"weg": "rsync"}) == ("alter Weg (direkt zum PC)", False)
    assert abgleich_zeile({"weg": "mitte", "fehler": "Mitte weg"})[1] is True
    text, warn = abgleich_zeile({"weg": "mitte", "letzter_erfolg": "2026-10-08T11:57:00",
                                 "hinweise": []}, jetzt)
    assert text == "über die Mitte · vor 3 Min" and warn is False
    text, warn = abgleich_zeile({"weg": "mitte", "letzter_erfolg": "2026-10-08T11:59:59",
                                 "hinweise": [{"am": "2026-10-08T11:00:00", "text": "x"},
                                              {"am": "2026-10-01T11:00:00", "text": "alt"},
                                              "müll"]}, jetzt)
    assert "gerade eben" in text and "1 Hinweis " in text and warn is True
    assert abgleich_zeile({"weg": "mitte", "letzter_erfolg": None})[1] is True
