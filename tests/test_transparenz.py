"""
Sichtbar machen, was sie tut — Tool-Calls und Denken im Chat.

Sasha, 20.08.2026, nach einem Turn, den niemand nachvollziehen konnte:

> „ganz wichtig machen wir im normalen chat einfach die tool calls usw
>  details was sie macht wie tool call, thinking, usw einfach alle
>  transparent und sichtbar, so wie man es bei dir claude sieht! das wird
>  schon helfen. weil keine ahnung was sie hier fabriziert hat."

Der Anlass: sie schrieb dieselbe Idee ZWEIMAL weg — beim ersten Mal als
sauberen Katalog-Eintrag, beim zweiten Mal als Prosa in dieselbe
Katalogdatei — und sagte beide Male nur „steht drin" bzw. „jetzt steht's
wirklich drin". Von aussen sah das aus wie eine Luege beim ersten Mal.
Sichtbare Tool-Calls haetten die Frage in einer Zeile beantwortet.

Zwei Enden werden geprueft: dass das Backend die Ereignisse ueberhaupt
hergibt, und dass die Anzeige daraus etwas Lesbares macht.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

from tui.zentrale_tui import werkzeug_zeile


# ── Was im Chat steht ─────────────────────────────────────────────────

def test_der_aufruf_zeigt_werkzeug_und_argumente():
    """WELCHE Datei sie beschrieben hat, ist genau die Frage, die man
    hinterher stellt. Nur den Namen zu zeigen beantwortet sie nicht."""
    rolle, text = werkzeug_zeile(
        {"phase": "start", "name": "write_note",
         "args": {"name": "ideen", "text": "Fraktal-Rendering"}})
    assert rolle == "werkzeug"
    assert "write_note" in text
    assert "name=ideen" in text
    assert "Fraktal-Rendering" in text


def test_lange_argumente_werden_gekuerzt_nicht_weggelassen():
    rolle, text = werkzeug_zeile(
        {"phase": "start", "name": "write_note",
         "args": {"text": "wort " * 100}})
    assert "wort" in text
    assert len(text) < 200


def test_das_ergebnis_steht_darunter():
    rolle, text = werkzeug_zeile(
        {"phase": "fertig", "name": "write_note",
         "text": "Notiert in kataloge/ideen."})
    assert rolle == "werkzeug_ergebnis"
    assert "kataloge/ideen" in text


def test_ein_fehler_ist_als_fehler_erkennbar():
    """Der Fall, in dem sie hinterher behauptet, es habe geklappt."""
    rolle, text = werkzeug_zeile(
        {"phase": "fehler", "name": "add_calendar_entry", "text": "kein Layer"})
    assert rolle == "werkzeug_fehler"
    assert "add_calendar_entry" in text and "kein Layer" in text


def test_zeilenumbrueche_im_ergebnis_werden_geglaettet():
    """Ein mehrzeiliges Tool-Ergebnis (read_calendar!) wuerde den Verlauf
    sonst sprengen."""
    _rolle, text = werkzeug_zeile(
        {"phase": "fertig", "name": "read_calendar",
         "text": "Montag\n  09:00 Uni\nDienstag\n  17:45 Geige"})
    assert "\n" not in text


def test_wirft_bei_muell_nicht():
    for w in ({}, {"phase": "start"}, {"phase": "quatsch", "name": "x"},
              {"phase": "start", "name": None, "args": None}):
        rolle, text = werkzeug_zeile(w)
        assert isinstance(rolle, str) and isinstance(text, str)


# ── Was das Backend hergibt ───────────────────────────────────────────

def test_der_cloud_pfad_meldet_start_und_ergebnis():
    """`run_tool` ist die einzige Stelle, durch die BEIDE Cloud-Dialekte
    gehen. Zweimal gepflegt hiesse, dass die Anzeige auf einer Schiene
    irgendwann fehlt."""
    import cloud

    ereignisse = []
    gen = cloud.run_tool("read_note", {"name": "ideen"},
                         tutor_mode=False,
                         active_exec=lambda n, a: "Inhalt der Ideen.",
                         user_query="", store=None)
    try:
        while True:
            ereignisse.append(gen.send(None))
    except StopIteration as ende:
        ausgang = ende.value

    werkzeuge = [e["werkzeug"] for e in ereignisse
                 if isinstance(e, dict) and "werkzeug" in e]
    phasen = [w["phase"] for w in werkzeuge]
    assert phasen == ["start", "fertig"]
    assert werkzeuge[0]["args"] == {"name": "ideen"}
    assert "Inhalt der Ideen." in werkzeuge[1]["text"]
    assert ausgang[0] == "result"


def test_ein_krachendes_werkzeug_meldet_den_fehler():
    """Sonst sieht man nur, dass sie hinterher etwas anderes sagt."""
    import cloud

    def kaputt(name, args):
        raise RuntimeError("Platte voll")

    ereignisse = []
    gen = cloud.run_tool("read_note", {"name": "x"}, tutor_mode=False,
                         active_exec=kaputt, user_query="", store=None)
    try:
        while True:
            ereignisse.append(gen.send(None))
    except StopIteration:
        pass

    fehler = [e["werkzeug"] for e in ereignisse
              if isinstance(e, dict) and "werkzeug" in e
              and e["werkzeug"]["phase"] == "fehler"]
    assert fehler and "Platte voll" in fehler[0]["text"]


def test_das_backend_reicht_das_ereignis_durch():
    """Der Stream-Endpunkt muss das Ereignis kennen — sonst faellt es
    zwischen Modell und Anzeige lautlos auf den Boden."""
    quelle = open(os.path.join(os.path.dirname(__file__), "..", "ui", "app.py"),
                  encoding="utf-8").read()
    assert "'werkzeug' in token" in quelle
