"""
Kompakte Leiste, '?'-Erklärung und Sortierer (2026-10-25,
tui/ansichten/fussleiste.py, tasten_zaehler.py). Sasha: „mach einfach nur die
shortcuts hin und wenn man ?+shortcut drückt dann wird die bedeutung
aufgeklappt, dazu ein kleiner sortierer mit the most used shortcuts ganz nach
vorne." Anlass: die Kalender-Hauptansicht brauchte ~255 Zeichen, das Terminal
hatte 160 Spalten — S (must/should) fehlte.
"""
import importlib.util
import json
import os

import pytest

import test_fussleiste as F
from test_fussleiste import welt  # noqa: F401  – Fixture: die TUI ohne Bildschirm
from tui import zentrale_tui as zt
from tui.ansichten import befehle, fussleiste, tasten_zaehler

_spec = importlib.util.spec_from_file_location(
    "tasten_zustaende_kalender_kompakt",
    os.path.join(os.path.dirname(__file__), "tasten_zustaende", "kalender.py"))
KAL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(KAL)


def _tasten(text):
    return [t.strip() for t in text.split(" · ")]


@pytest.mark.parametrize("ansicht", ["a:termine", "b:monat", "c:woche"])
def test_kalender_leiste_hat_S_bei_100_spalten(welt, ansicht):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE[ansicht])
    assert u.kalender.ansicht() == ansicht
    text, _farbe = fussleiste.leistenzeile(u, 100)
    assert len(text) <= 100
    assert "S" in _tasten(text), text
    assert "…" not in text                       # alle Tasten passen
    assert _tasten(text)[-2:] == ["/", "?"]
    assert "must/should" not in text             # keine Beschriftung mehr


def test_fragezeichen_erklaert_eine_taste_und_schliesst(welt):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE["b:monat"])
    vorher = F.fingerabdruck(u)
    zt.taste_verteilen(u, ord("?"))
    assert fussleiste.leistenzeile(u, 100)[0].strip() == fussleiste.TEXT_WARTEN
    zt.taste_verteilen(u, ord("S"))              # wird erklärt, NICHT ausgeführt
    text, farbe = fussleiste.leistenzeile(u, 100)
    assert text == " S  must/should" and farbe == fussleiste.FARBE_ERKLAERUNG
    assert F.fingerabdruck(u) == vorher
    zt.taste_verteilen(u, -1)                    # Timeout schließt nicht
    assert fussleiste.erklaert(u.z)
    zt.taste_verteilen(u, ord("x"))              # nächste Taste schließt
    assert not fussleiste.erklaert(u.z) and F.fingerabdruck(u) == vorher


def test_erklaerung_von_zweitbelegung_und_unbelegtem(welt):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE["a:termine"])
    t, w = fussleiste.erklaerung(u, "k")
    assert t == "k" and "like" in w
    assert fussleiste.erklaerung(u, "/")[0] == "/"
    assert fussleiste.erklaerung(u, "ctrl+z")[1] == "does nothing here"


def test_fragezeichen_im_freitext_bleibt_ein_zeichen(welt):
    u = F._aufgebaut(welt, F._chat_text)
    assert not fussleiste.frage_frei(u.z)
    zt.taste_verteilen(u, ord("?"))
    assert not fussleiste.erklaert(u.z)


def test_any_key_frage_behaelt_das_fragezeichen(welt):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE["ansehen"])
    assert not fussleiste.frage_frei(u.z)        # „any key" nimmt auch '?'


def test_kein_programm_belegt_das_fragezeichen_selbst(welt):
    """Stand 25.10.2026: nur Freitext und „any key"-Fragen nehmen '?'. Belegt
    ein Programm '?' künftig selbst, gewinnt es (frage_frei) — dann hier
    eintragen und in memory/system/tastentabelle.md nennen."""
    u = welt()
    selbst = []
    for n, p in u.z.programme.items():
        tab = getattr(p, "TASTEN", None)
        for a in (tab.ansichten() if tab else []):
            if "?" in tab._karte.get(a, {}):
                selbst.append((n, a))
    assert selbst == []


def test_hilfe_und_befehlsfenster_bleiben_beschriftet(welt):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE["b:monat"])
    _titel, eintr = fussleiste.programm_tasten(u)
    assert ("S", "must/should") in eintr
    h = dict(fussleiste.hilfe(u))
    assert "must/should" in h["kalender"]
    _t, rows = befehle.overlay_rows("/help", True, None, fussleiste.hilfe(u))
    assert rows


def test_sortierer_meistgenutzt_vorne_und_springt_nicht(welt):
    u = F._aufgebaut(welt, KAL.ZUSTAENDE["b:monat"])
    vorher = _tasten(fussleiste.leistenzeile(u, 200)[0])
    assert vorher[0] != "S"
    for _ in range(3):
        zt.taste_verteilen(u, ord("S"))
    # Noch in derselben Ansicht: die Leiste steht still.
    assert _tasten(fussleiste.leistenzeile(u, 200)[0]) == vorher
    z = fussleiste.leiste_von(u.z).zaehler
    assert z.anzahl("kalender", "b:monat", "S") == 3
    zt.taste_verteilen(u, ord("j"))              # Zweitbelegung zählt für ↓/↑
    # Ansicht wechseln und zurück: jetzt neu sortiert, S vorn, keiner fehlt.
    z.sortiert("kalender", "c:woche", [])
    nachher = _tasten(fussleiste.leistenzeile(u, 200)[0])
    assert nachher[0] == "S" and sorted(nachher) == sorted(vorher)
    # Gespeichert beim Ansichtswechsel.
    with open(z.datei) as f:
        assert json.load(f)["kalender"]["b:monat"]["S"] == 3


def test_sortierer_reihenfolge_bei_gleichstand_wie_tabelle(tmp_path):
    z = tasten_zaehler.Zaehler(str(tmp_path / "z.json"))
    e = [("a", ""), ("b", ""), ("c", ""), ("d", "")]
    z.zaehlen("p", "v", "c"); z.zaehlen("p", "v", "c"); z.zaehlen("p", "v", "d")
    assert [t for t, _ in z.sortiert("p", "v", e)] == ["c", "d", "a", "b"]


@pytest.mark.parametrize("inhalt", ["{kaputt", "[1, 2]", '{"p": {"v": {"a": "x", "b": 2}}}'])
def test_kaputte_zaehlerdatei(tmp_path, inhalt):
    pfad = tmp_path / "z.json"
    pfad.write_text(inhalt)
    z = tasten_zaehler.Zaehler(str(pfad))
    e = [("a", ""), ("b", "")]
    if inhalt.startswith('{"p"'):                # Form stimmt, Teile nicht: Rest bleibt
        assert z.anzahl("p", "v", "b") == 2 and z.anzahl("p", "v", "a") == 0
        assert [t for t, _ in z.sortiert("p", "v", e)] == ["b", "a"]
        return
    assert z.meldung and (tmp_path / "z.json.kaputt").exists()   # nie still
    assert z.sortiert("p", "v", e) == e
    z.zaehlen("p", "v", "b"); z.speichern()
    assert json.loads(pfad.read_text()) == {"p": {"v": {"b": 1}}}


def test_fehlende_zaehlerdatei_und_ordner(tmp_path):
    z = tasten_zaehler.Zaehler(str(tmp_path / "neu" / "z.json"))
    assert z.meldung == "" and z.sortiert("p", "v", [("a", "")]) == [("a", "")]
    z.zaehlen("p", "v", "a"); z.speichern()
    assert (tmp_path / "neu" / "z.json").exists()


def test_zaehler_liegt_nie_im_repo(monkeypatch):
    monkeypatch.delenv("ZENTRALE_TASTEN_ZAEHLER")
    monkeypatch.setenv("XDG_STATE_HOME", "/x/state")
    assert tasten_zaehler.pfad() == "/x/state/zentrale/tasten_zaehler.json"
