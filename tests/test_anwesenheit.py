"""
Ist Sasha da? Und schaut er ZENTRALE an?

Sashas Vorgabe (20.08.2026): *„die anwesenheit wird per code assessed …
dann kriegt die ai einfach nur ein is da, is nich da."* Genau darum geht es
hier — die KI soll keine Millisekunden sehen und nicht ueber Leerlaufzeiten
spekulieren, sondern eine fertige Lage bekommen.

Getestet wird gegen gestellte Messwerte. Die echten Quellen (X11-Leerlauf
per ctypes, logind, i3) sind auf der Maschine geprueft worden; hier geht es
darum, dass die SCHLUESSE daraus nicht verrutschen.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import anwesenheit as a


@pytest.fixture
def lage(monkeypatch):
    """(leerlauf_minuten, gesperrt, zentrale_sichtbar) stellen -> lage()."""
    import melden

    def stellen(minuten=0, gesperrt=False, sichtbar=False):
        monkeypatch.setattr(a, "gesperrt", lambda: gesperrt)
        monkeypatch.setattr(
            a, "leerlauf_ms",
            lambda: None if minuten is None else int(minuten * 60_000))
        monkeypatch.setattr(melden, "sichtbar", lambda: sichtbar)
        return a.lage()
    return stellen


# ── Die drei Lagen ────────────────────────────────────────────────────

def test_zentrale_offen(lage):
    assert lage(minuten=1, sichtbar=True) == a.OFFEN


def test_am_rechner_aber_zentrale_zu(lage):
    assert lage(minuten=1, sichtbar=False) == a.WOANDERS


def test_lange_nichts_getippt_heisst_weg(lage):
    assert lage(minuten=a.LEERLAUF_MIN + 1) == a.WEG


def test_gesperrt_heisst_weg_egal_was_die_uhr_sagt(lage):
    """Eine gerade gesperrte Maschine hat eine winzige Leerlaufzeit — ohne
    diesen Vorrang waere er in der Minute nach dem Sperren 'anwesend'."""
    assert lage(minuten=0, gesperrt=True) == a.WEG


def test_gesperrt_schlaegt_auch_ein_sichtbares_fenster(lage):
    """Hinter dem Sperrbildschirm steht ZENTRALE unveraendert offen — i3
    weiss davon nichts."""
    assert lage(minuten=0, gesperrt=True, sichtbar=True) == a.WEG


def test_lesen_zaehlt_noch_als_anwesend(lage):
    """Wer liest, tippt nicht. Eine knappe Schwelle erklaerte ihn mitten im
    Lesen fuer abwesend."""
    assert lage(minuten=a.LEERLAUF_MIN - 1) == a.WOANDERS


# ── Wenn sich nichts messen laesst ────────────────────────────────────

def test_ohne_jede_messung_unbekannt(lage):
    """Kein X, kein i3 — auf dem Pi der Normalfall."""
    assert lage(minuten=None, sichtbar=None) == a.UNBEKANNT


def test_ohne_x_aber_mit_sichtbarem_fenster_gilt_offen(lage):
    assert lage(minuten=None, sichtbar=True) == a.OFFEN


def test_ohne_x_und_fenster_zu_wird_wie_abgewandt_behandelt(lage):
    """Lieber einmal zu viel gemeldet als eine Erinnerung verschluckt."""
    assert lage(minuten=None, sichtbar=False) == a.WOANDERS


def test_ein_kaputtes_melden_reisst_nichts_mit(monkeypatch):
    import melden
    monkeypatch.setattr(a, "gesperrt", lambda: False)
    monkeypatch.setattr(a, "leerlauf_ms", lambda: 0)
    def kaputt():
        raise RuntimeError("weg")
    monkeypatch.setattr(melden, "sichtbar", kaputt)
    assert a.lage() == a.WOANDERS


# ── Was die KI davon sieht ────────────────────────────────────────────

def test_die_ki_bekommt_einen_satz_keine_messwerte():
    """Millisekunden im Prompt waeren eine Einladung, daraus etwas
    abzuleiten — und Modelle rechnen an solchen Zahlen gern vorbei."""
    for welche in (a.OFFEN, a.WOANDERS, a.WEG, a.UNBEKANNT):
        text = a.satz(welche)
        assert "Sasha" in text or "sasha" in text
        assert not any(z.isdigit() for z in text)


def test_die_saetze_sind_unterscheidbar():
    saetze = {a.satz(w) for w in (a.OFFEN, a.WOANDERS, a.WEG, a.UNBEKANNT)}
    assert len(saetze) == 4


def test_unbekannte_lage_faellt_auf_unbekannt_zurueck():
    assert a.satz("quatsch") == a.satz(a.UNBEKANNT)


# ── Die Messung selbst (nur: wirft nicht) ─────────────────────────────

def test_leerlauf_wirft_nie(monkeypatch):
    """Ohne X-Server (Testlauf, Pi, ssh) darf das nicht fliegen, sondern
    muss sauber 'weiss ich nicht' sagen."""
    monkeypatch.delenv("DISPLAY", raising=False)
    assert a.leerlauf_ms() is None or isinstance(a.leerlauf_ms(), int)


def test_gesperrt_wirft_nie():
    assert isinstance(a.gesperrt(), bool)
