"""
Der Takt — wann ZENTRALE von sich aus etwas sagt.

Getestet wird die Entscheidung, nicht die Ausfuehrung: `faellig()` macht
keinen Modell-Aufruf und beruehrt kein Netz. Das ist Absicht — ein Fehler
in der Anstoss-Logik soll hier auffallen und nicht erst, wenn er Geld
gekostet hat.

Die Tests sind ueberwiegend Tests gegen ZU VIEL Reden. Dass ein Anstoss
mal ausbleibt, merkt man und aergert sich kurz; ein Assistent, der dreimal
mahnt, wird abgeschaltet.
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
import takt


@pytest.fixture
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    monkeypatch.setattr(takt, "_DATA_DIR", str(tmp_path / "takt"))
    kalender.add_entry("termine", "2026-08-18", "Geigenstunde", time="17:45")
    return takt


def _um(h, m):
    return datetime(2026, 8, 18, h, m)


# ── Die Schwellen ─────────────────────────────────────────────────────

def test_eine_stunde_vorher_stoesst_an(welt):
    a = welt.faellig(_um(16, 45))
    assert a and "Geigenstunde" in a["auftrag"]


def test_eine_halbe_stunde_vorher_stoesst_an(welt):
    assert welt.faellig(_um(17, 15)) is not None


def test_dazwischen_wird_geschwiegen(welt):
    """Der Sinn der Schwellen: zweimal, nicht dauernd."""
    assert welt.faellig(_um(16, 20)) is None
    assert welt.faellig(_um(16, 30)) is None
    assert welt.faellig(_um(17, 5)) is None


def test_kurz_davor_kommt_nichts_mehr(welt):
    """Fuenf Minuten vorher hilft eine Mahnung niemandem mehr."""
    assert welt.faellig(_um(17, 40)) is None


def test_ein_verspaeteter_tick_holt_nach(welt):
    """Der Treiber laeuft im Minutentakt, aber ein Rechner schlaeft mal
    kurz. Ohne Nachlauf faellt der Anstoss dann stillschweigend aus."""
    assert welt.faellig(_um(16, 47)) is not None


def test_der_nachlauf_bleibt_knapp(welt):
    """Zu grosszuegig, und die Stunden-Mahnung kaeme bei 40 Minuten an —
    also direkt vor der halbstuendigen. Dann sind es doch wieder zwei
    Mahnungen hintereinander."""
    assert welt.faellig(_um(16, 55)) is None


# ── Jeder Anstoss genau einmal ────────────────────────────────────────

def test_gemerkter_anstoss_kommt_nicht_wieder(welt):
    a = welt.faellig(_um(16, 45))
    welt.merken(a["marke"], _um(16, 45))
    assert welt.faellig(_um(16, 46)) is None


def test_der_zustand_ueberlebt_einen_neustart(welt):
    """Im Speicher zu merken hiesse: nach jedem Backend-Neustart mahnt sie
    alles noch einmal."""
    ordner = welt._DATA_DIR          # VOR dem Reload merken: `welt` ist
    a = welt.faellig(_um(16, 45))    # dasselbe Modulobjekt, reload setzt
    welt.merken(a["marke"], _um(16, 45))   # seine Attribute zurueck.
    import importlib
    importlib.reload(takt)
    takt._DATA_DIR = ordner
    assert takt.faellig(_um(16, 46)) is None


def test_die_halbe_stunde_kommt_trotz_der_ganzen(welt):
    """Die beiden Schwellen sind getrennte Anstoesse — sonst waere die
    zweite durch die erste erledigt."""
    a = welt.faellig(_um(16, 45))
    welt.merken(a["marke"], _um(15, 0))      # lange her, kein Abstandsproblem
    assert welt.faellig(_um(17, 15)) is not None


# ── Schweigeregeln ────────────────────────────────────────────────────

def test_nachts_wird_geschwiegen(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    monkeypatch.setattr(takt, "_DATA_DIR", str(tmp_path / "takt"))
    kalender.add_entry("termine", "2026-08-19", "Fruehschicht", time="06:00")
    assert takt.faellig(datetime(2026, 8, 19, 5, 0)) is None


def test_mindestabstand_zwischen_zwei_anstoessen(welt):
    """Auch verschiedene Anstoesse duerfen nicht im Minutenabstand kommen."""
    welt.merken("irgendwas", _um(16, 40))
    assert welt.faellig(_um(16, 45)) is None


def test_ohne_termin_kein_anstoss(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    monkeypatch.setattr(takt, "_DATA_DIR", str(tmp_path / "takt"))
    assert takt.faellig(_um(16, 45)) is None


def test_morgen_ist_kein_countdown_fall(tmp_path, monkeypatch):
    """Am Abend ist der naechste Termin einer von morgen. Ihn hier zu
    behandeln hiesse, um 22 Uhr an die Vorlesung um 8 zu erinnern — das
    gehoert ins Schemen, nicht in eine Stunden-Schwelle."""
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    monkeypatch.setattr(takt, "_DATA_DIR", str(tmp_path / "takt"))
    kalender.add_entry("termine", "2026-08-19", "Vorlesung", time="08:00")
    assert takt.faellig(datetime(2026, 8, 18, 21, 0)) is None


def test_ein_kaputter_kalender_laesst_es_bleiben(welt, monkeypatch):
    """Lieber still als laut falsch."""
    def kaputt(*a, **k):
        raise RuntimeError("weg")
    monkeypatch.setattr(kalender, "naechster_termin", kaputt)
    assert welt.faellig(_um(16, 45)) is None


# ── Der Auftrag ───────────────────────────────────────────────────────

def test_der_auftrag_ist_ein_auftrag_keine_fertige_nachricht(welt):
    """Was gesagt wird, formuliert das Modell — es kennt den Verlauf und
    weiss, ob Sasha gerade mitten in etwas steckt. Der Code entscheidet
    nur das WANN."""
    a = welt.faellig(_um(16, 45))
    assert "Erinnere" in a["auftrag"]
    assert "17:45" in a["auftrag"]
    assert "kein Countdown" in a["auftrag"]


# ── Der Treiber (ui/app.py) ───────────────────────────────────────────

def test_der_auftrag_landet_nicht_im_verlauf(monkeypatch):
    """Der Auftrag ist eine Regieanweisung, keine Aeusserung von Sasha. Ihn
    mitzuspeichern hiesse, dass er morgen Saetze in seinem Verlauf liest,
    die er nie geschrieben hat — und dass das Modell sie als seine liest."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    import ai
    import ai_backends
    import app
    import state

    gesehen = {}

    def fake_stream(history, **kw):
        gesehen["letzte"] = history[-1]
        yield {"reflect": "denkt nach"}      # Nicht-Text wird ignoriert
        yield "Geige gleich. "
        yield "Los."

    monkeypatch.setattr(ai_backends, "chat_available", lambda: "local")
    monkeypatch.setattr(ai, "chat_stream", fake_stream)
    vorher = len(state.get_chat_history())

    assert app._takt_sprechen({"marke": "x", "auftrag": "Erinnere ihn an X."})

    verlauf = state.get_chat_history()
    assert gesehen["letzte"]["role"] == "user"
    assert gesehen["letzte"]["content"].startswith("Erinnere ihn an X.")
    assert len(verlauf) == vorher + 1
    assert verlauf[-1]["role"] == "assistant"
    assert verlauf[-1]["content"] == "Geige gleich. Los."
    assert all("Erinnere ihn an X." not in m["content"] for m in verlauf)


def test_ohne_erreichbares_backend_wird_geschwiegen(monkeypatch):
    """Auf dem Laptop ohne Ollama und ohne Netz gaebe es sonst jede Minute
    einen Anlauf gegen ein Backend, das es nicht gibt."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    import ai_backends
    import app
    import state

    monkeypatch.setattr(ai_backends, "chat_available", lambda: None)
    vorher = len(state.get_chat_history())
    assert app._takt_sprechen({"marke": "x", "auftrag": "y"}) is False
    assert len(state.get_chat_history()) == vorher


def test_eine_leere_antwort_wird_nicht_abgelegt(monkeypatch):
    """Ein stummer Turn (gemessen: das billige Modell nach einem Tool-Call)
    wuerde sonst als leere Blase im Chat stehen."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    import ai
    import ai_backends
    import app
    import state

    monkeypatch.setattr(ai_backends, "chat_available", lambda: "local")
    monkeypatch.setattr(ai, "chat_stream", lambda h, **k: iter(["  "]))
    vorher = len(state.get_chat_history())
    assert app._takt_sprechen({"marke": "x", "auftrag": "y"}) is False
    assert len(state.get_chat_history()) == vorher


# ── In welche Lage hinein sie spricht ─────────────────────────────────

def _treiber(monkeypatch, lage):
    """Den Treiber mit gestellter Lage und gefaelschtem Modell fahren.
    -> (was das Modell als letzte Nachricht sah, was gemeldet wurde)"""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ui"))
    import ai
    import ai_backends
    import anwesenheit
    import app
    import melden

    gesehen, gemeldet = {}, []

    def fake_stream(history, **kw):
        gesehen["letzte"] = history[-1]["content"]
        yield "Geige gleich."

    monkeypatch.setattr(ai_backends, "chat_available", lambda: "local")
    monkeypatch.setattr(ai, "chat_stream", fake_stream)
    monkeypatch.setattr(anwesenheit, "lage", lambda: lage)
    monkeypatch.setattr(melden, "desktop",
                        lambda text, **kw: gemeldet.append(text) or True)
    app._takt_sprechen({"marke": "x", "auftrag": "Erinnere ihn an X."})
    return gesehen["letzte"], gemeldet


def test_bei_offener_zentrale_kein_popup(monkeypatch):
    """Sie hat seine Aufmerksamkeit schon — ein Popup waere reine Stoerung."""
    import anwesenheit
    auftrag, gemeldet = _treiber(monkeypatch, anwesenheit.OFFEN)
    assert gemeldet == []
    assert "offen" in auftrag.lower()
    assert "Einblendung" not in auftrag


def test_bei_geschlossener_zentrale_wird_gemeldet(monkeypatch):
    """Er arbeitet an etwas anderem: erst Aufmerksamkeit holen."""
    import anwesenheit
    auftrag, gemeldet = _treiber(monkeypatch, anwesenheit.WOANDERS)
    assert gemeldet == ["Geige gleich."]
    assert "Einblendung" in auftrag
    assert "in den Chat" in auftrag


def test_abwesend_wird_trotzdem_gemeldet(monkeypatch):
    """Er sieht es, wenn er zurueckkommt. Zu schweigen hiesse, die
    Erinnerung ganz zu verlieren."""
    import anwesenheit
    _, gemeldet = _treiber(monkeypatch, anwesenheit.WEG)
    assert gemeldet == ["Geige gleich."]


def test_unbekannte_lage_wird_wie_abgewandt_behandelt(monkeypatch):
    """Wer nicht weiss, ob jemand hinschaut, meldet lieber einmal zu viel."""
    import anwesenheit
    _, gemeldet = _treiber(monkeypatch, anwesenheit.UNBEKANNT)
    assert gemeldet == ["Geige gleich."]


# ── Aufraeumen ────────────────────────────────────────────────────────

def test_alte_tageszustaende_werden_entsorgt(welt):
    """Sonst waechst der Ordner um eine Datei pro Tag, fuer immer."""
    for tag in range(1, 16):
        welt._schreiben({"erledigt": []}, date(2026, 8, tag))
    assert welt.aufraeumen(behalten=7) == 8
    assert len(os.listdir(welt._DATA_DIR)) == 7
