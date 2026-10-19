"""
Bearbeiten kollidiert nicht mit sich selbst (19.10.2026).

Anlass: Sasha änderte per Stylebox nur das Aussehen eines Termins — die
Rückfrage meldete „überlappt komplett mit" demselben Termin. Die Prüfung
(conflicts_for_proposed) hängte die neue Fassung an die Einträge des Tages,
darunter die alte. Jetzt:
  * ohne Änderung an Tag/Zeit schickt das Formular gar keine Prüfung,
  * mit Änderung trägt die Prüfung `ausser` = Kennung des Termins,
  * eine echte Kollision mit einem ANDEREN Termin fragt weiter nach.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import pytest

import kalender
from tui.ansichten import kalender_werkzeuge as kw

TAG = date(2026, 10, 7)
ISO = TAG.isoformat()


# ── Kern: `ausser` nimmt den Eintrag selbst heraus ────────────────────
@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    kalender.add_entry("termine", ISO, "Zahnarzt", time="14:00", ende="15:00")
    kalender.add_entry("termine", ISO, "Kino", time="19:00", ende="21:00")
    kalender.add_routine("termine", "Geige", "FREQ=DAILY", time="10:00", ende="11:00")
    return tmp_path


def _kennung(label):
    import kalender_kennung as kk
    return next(e["kennung"] for e in kk.alle_eintraege() if e["label"] == label)


@pytest.mark.kalender_beide
def test_kern_selbst_zaehlt_nicht(cal):
    k = _kennung("Zahnarzt")
    assert kalender.conflicts_for_proposed("termine", ISO, "Zahnarzt", "14:30", "15:30")
    assert kalender.conflicts_for_proposed("termine", ISO, "Zahnarzt", "14:30", "15:30",
                                           ausser=k) == []


@pytest.mark.kalender_beide
def test_kern_routinen_vorkommen_am_tag_raus(cal):
    k = _kennung("Geige")
    assert kalender.conflicts_for_proposed("termine", ISO, "Geige", "10:15", "11:15",
                                           ausser=k) == []


@pytest.mark.kalender_beide
def test_kern_andere_kollision_bleibt(cal):
    w = kalender.conflicts_for_proposed("termine", ISO, "Zahnarzt", "20:00", "21:30",
                                        ausser=_kennung("Zahnarzt"))
    assert any("Kino" in z for z in w)


# ── TUI-Plan: was das Formular beim Bearbeiten prüfen lässt ───────────
ZAHN = {"label": "Zahnarzt", "layer": "termine", "time": "14:00", "ende": "15:00",
        "kennung": "k-zahn"}


def _setze(f, **werte):
    for name, wert in werte.items():
        next(x for x in f.felder if x.name == name).text = wert
    return f.taste(10)


def test_bearbeiten_ohne_zeitaenderung_keine_pruefung():
    f = kw.formular_bearbeiten(ZAHN, TAG, TAG)
    assert _setze(f, titel="Zahnarzt Dr. B") == "fertig"
    assert not f.plan().get("konflikt")


def test_bearbeiten_mit_zeitaenderung_prueft_ohne_sich_selbst():
    f = kw.formular_bearbeiten(ZAHN, TAG, TAG)
    _setze(f, von="14:30", bis="15:30")
    assert f.plan()["konflikt"] == {"day": ISO, "label": "Zahnarzt", "time": "14:30",
                                    "ende": "15:30", "ausser": "k-zahn"}
