"""
Tastentabellen (2026-10-11, tui/ansichten/tasten.py, horcher.py,
core/tastentabelle.py). Sasha: die Leiste ganz unten zeigt nur, was in der
offenen Ansicht wirklich geht — und zwar nicht von Hand geschrieben, sondern
aus der Tabelle, aus der das Programm auch seine Tasten verteilt.

Für jedes Programm mit Tabelle verlangt der Test:
  - jede Aktion hat eine Methode aktion_<name>;
  - zu jeder Ansicht der Tabelle einen Weg dorthin
    (tests/tasten_zustaende/<programm>.py: ZUSTAENDE = {ansicht: aufbau});
  - dort zeigt die echte Leiste genau die Tabelle (plus „/ commands", wo '/'
    die Befehlszeile öffnet);
  - JEDE Taste der Tabelle (auch die ungezeigten) tut dort etwas.
"""
import curses
import importlib.util
import os
import types

import pytest

import test_fussleiste as F
from test_fussleiste import welt  # noqa: F401  – Fixture: die TUI ohne Bildschirm
from tui import ansichten as A
from tui.ansichten import fussleiste, horcher, tasten
from tui.ansichten.basis import BEENDEN
from tui.ansichten.fenster import PROGRAMME, STARTSEITE, aktives_programm

tt = tasten.tt
ORDNER = os.path.join(os.path.dirname(__file__), "tasten_zustaende")
NAMEN = [n for _d, n in PROGRAMME] + [STARTSEITE]


def _zustaende():
    raus = {}
    for datei in sorted(os.listdir(ORDNER)):
        if datei.endswith(".py") and not datei.startswith("_"):
            spec = importlib.util.spec_from_file_location(
                "tasten_zustaende_" + datei[:-3], os.path.join(ORDNER, datei))
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)
            raus[datei[:-3]] = modul.ZUSTAENDE
    return raus


ZUSTAENDE = _zustaende()
# None = die Ansicht kommt in diesem Programm nicht vor (ein Baustein bringt
# sie mit, z. B. die leere Stylebox, die der Kalender nie zeigt).
FAELLE = [(p, a) for p, z in ZUSTAENDE.items() for a, auf in z.items() if auf is not None]


def _programm(u, name):
    p = u.z.programme.get(name)
    if getattr(p, "TASTEN", None) is None:
        pytest.skip("%s hat noch keine Tastentabelle" % name)
    return p


# ── Format (core/tastentabelle.py) ────────────────────────────────────

def test_beschriftungen_werden_zu_tastennamen():
    assert tt.namen("↑↓") == ["up", "down"]
    assert tt.namen("a/s") == ["a", "s"]
    assert tt.namen("/") == ["/"]
    assert tt.namen("+/-") == ["+", "-"]
    assert tt.namen("alt+←→") == ["alt+left", "alt+right"]
    assert tt.namen("shift+↑↓←→") == ["shift+up", "shift+down", "shift+left", "shift+right"]
    assert tt.namen("ctrl+C") == ["ctrl+c"]
    assert tt.namen("pgup pgdn") == ["pgup", "pgdn"]
    assert tt.namen("⌫") == ["backspace"]
    assert tt.namen("type") == [] and tt.namen("any key") == []
    with pytest.raises(ValueError):
        tt.namen("bild↑↓")


def test_pruefen_findet_fehler():
    assert tt.pruefen({"a": [{"taste": "d", "aktion": "weg", "text": "delete"}]}) == []
    assert tt.pruefen({"a": [{"taste": "d", "aktion": "weg"},
                             {"taste": "x/d", "aktion": "anders"}]})       # d doppelt
    assert tt.pruefen({"a": [{"taste": "d", "aktion": "Weg!"}]})          # Aktionsname
    assert tt.pruefen({"a": [{"taste": "zz", "aktion": "weg"}]})          # unlesbar
    assert tt.pruefen({"a": [{"taste": "d", "aktion": "weg", "farbe": 1}]})
    assert tt.pruefen([]) == ["tastentabelle ist kein objekt"]


def test_manifest_traegt_die_tabelle():
    m = {"name": "x", "tasten": {"start": [{"taste": "enter", "aktion": "los", "text": "go"}]}}
    assert tt.aus_manifest(m) == m["tasten"]
    assert tt.aus_manifest({"name": "x"}) is None
    assert tt.aus_manifest({"name": "x", "tasten": {"s": [{"taste": "??", "aktion": "a"}]}}) is None


# ── Verteilen (tui/ansichten/tasten.py) ───────────────────────────────

class _Spiel:
    TASTEN = tasten.Tasten({
        "start": [("↑↓", "gehen", "move"), ("k", "gehen"), ("alt+←", "zurueck", "back"),
                  ("q", "ende", "quit")],
        "tippen": [("type", "tippen", "type"), ("esc", "fertig", "done"),
                   ("any key", "sonst")],
    })

    def __init__(self):
        self.z = types.SimpleNamespace(stdscr=F.Schirm())
        self.log, self.modus = [], "start"

    def ansicht(self):
        return self.modus

    def taste(self, ch):
        return self.TASTEN.verteilen(self, self.ansicht(), ch)

    def aktion_gehen(self, t): self.log.append(("gehen", t))
    def aktion_zurueck(self, t): self.log.append(("zurueck", t))
    def aktion_ende(self, t): return BEENDEN
    def aktion_tippen(self, t): self.log.append(("tippen", t))
    def aktion_fertig(self, t): self.log.append(("fertig", t))
    def aktion_sonst(self, t): self.log.append(("sonst", t))


def test_tabelle_verteilt_neutrale_namen():
    s = _Spiel()
    s.taste(curses.KEY_UP); s.taste(ord("k"))
    s.z.stdscr.folge = [curses.KEY_LEFT]; s.taste(27)          # Esc + Pfeil = alt+←
    assert s.log == [("gehen", "up"), ("gehen", "k"), ("zurueck", "alt+left")]
    assert s.taste(ord("q")) == BEENDEN
    assert s.taste(ord("x")) is None and len(s.log) == 3       # nicht belegt: nichts
    assert s.TASTEN.eintraege("start") == [("↑↓", "move"), ("alt+←", "back"), ("q", "quit")]


def test_shift_pfeile_kommen_als_eigene_namen():
    """Desk (2026-10-11): curses meldet Shift+Pfeile als KEY_SR/KEY_SF/
    KEY_SLEFT/KEY_SRIGHT — sie heißen shift+up … und gehen hin und zurück."""
    for n in ("shift+up", "shift+down", "shift+left", "shift+right"):
        (code,) = tasten.codes(n)
        assert tasten.name_von(code) == n


def test_shift_pfeile_in_den_anderen_formen(monkeypatch):
    """Terminals ohne KEY_SR …: eigener Keycode kUP2 … oder roh ESC [1;2A."""
    monkeypatch.setattr(curses, "keyname", lambda c: b"kLFT2" if c == 600 else b"")
    assert tasten.name_von(600) == "shift+left"
    schirm = F.Schirm()
    schirm.folge = [ord(c) for c in "[1;2B"]
    assert tasten.name_von(27, schirm, alt=True) == "shift+down"


def test_teile_bringen_ihre_tabelle_mit():
    class Teil:
        TASTEN = tasten.Tasten({"liste": [("enter", "nehmen", "take")]})
        def __init__(self): self.log = []
        def aktion_nehmen(self, t): self.log.append(t)

    class Ganz:
        def __init__(self):
            self.teil, self.offen = Teil(), False
        TASTEN = tasten.Tasten.zusammen({"start": [("esc", "zu", "close")]},
                                        {"teil": (Teil.TASTEN, lambda p: p.teil)})
        def aktion_zu(self, t): pass

    g = Ganz()
    assert sorted(g.TASTEN.ansichten()) == ["start", "teil:liste"]
    g.TASTEN.verteilen(g, "teil:liste", 10)
    assert g.teil.log == ["enter"] and g.TASTEN.fehlende_methoden(g) == []


def test_freitext_und_jede_taste():
    s = _Spiel(); s.modus = "tippen"
    s.taste(ord("a")); s.taste(32); s.taste(27); s.taste(curses.KEY_DOWN)
    assert s.log == [("tippen", "a"), ("tippen", " "), ("fertig", "esc"), ("sonst", "down")]
    assert s.TASTEN.freitext("tippen") and not s.TASTEN.freitext("start")


# ── Horcher (tui/ansichten/horcher.py) ────────────────────────────────

def test_horcher_merkt_die_tabelle_beim_verkabeln():
    h = horcher.Horcher()
    h.verkabeln("spiel", _Spiel())
    assert h.herkunft("spiel") == "tabelle"
    assert h.eintraege("spiel", "start") == [("↑↓", "move"), ("alt+←", "back"), ("q", "quit")]
    assert h.freitext("spiel", "tippen") and sorted(h.ansichten("spiel")) == ["start", "tippen"]


def test_horcher_liest_das_manifest():
    h = horcher.Horcher()
    h.verkabeln("app", object(), manifest={
        "name": "app", "tasten": {"start": [{"taste": "enter", "aktion": "los", "text": "go"}]}})
    assert h.herkunft("app") == "manifest" and h.eintraege("app", "start") == [("enter", "go")]


class _OhneTabelle:
    """Ein Programm ohne Tabelle: a zählt, enter öffnet „innen", dort esc zurück."""

    def __init__(self):
        self.z = types.SimpleNamespace(stdscr=F.Schirm())
        self.zustand = {"n": 0, "innen": False}

    def ansicht(self):
        return "innen" if self.zustand["innen"] else "start"

    def taste(self, ch):
        if self.zustand["innen"]:
            if ch == 27:
                self.zustand["innen"] = False
        elif ch == ord("a"):
            self.zustand["n"] += 1
        elif ch == 10:
            self.zustand["innen"] = True


def test_horcher_hoert_ab_wenn_keine_tabelle_da_ist():
    h = horcher.Horcher()
    h.verkabeln("fremd", _OhneTabelle(), fabrik=_OhneTabelle, im_hintergrund=False)
    assert h.herkunft("fremd") == "abgehört"
    assert [t for t, _ in h.eintraege("fremd", "start")] == ["enter", "a"]
    assert [t for t, _ in h.eintraege("fremd", "innen")] == ["esc"]


# ── Jedes Programm der TUI ────────────────────────────────────────────

@pytest.mark.parametrize("name", NAMEN)
def test_jede_aktion_hat_eine_methode(welt, name):
    p = _programm(welt(), name)
    fehlt = p.TASTEN.fehlende_methoden(p)
    assert not fehlt, "%s: aktion ohne methode: %s" % (name, fehlt)


@pytest.mark.parametrize("name", NAMEN)
def test_jede_ansicht_hat_einen_weg_im_test(welt, name):
    p = _programm(welt(), name)
    assert set(p.TASTEN.ansichten()) == set(ZUSTAENDE.get(name, {})), \
        "tests/tasten_zustaende/%s.py: ZUSTAENDE passt nicht zur tabelle" % name


@pytest.mark.parametrize("name,ansicht", FAELLE)
def test_jede_taste_der_tabelle_tut_etwas(welt, name, ansicht):
    aufbau = ZUSTAENDE[name][ansicht]
    u = F._aufgebaut(welt, aufbau)
    p = _programm(u, name)
    assert aktives_programm(u.z) == name and p.ansicht() == ansicht
    # Die Leiste zeigt genau die Tabelle (der Horcher hat sie beim Verkabeln).
    gezeigt = [e for e in fussleiste.eintraege(u) if e != ("/", "commands")]
    assert gezeigt == p.TASTEN.eintraege(ansicht)
    tot = []
    for e in p.TASTEN.daten()[ansicht]:
        for n in tt.namen(e["taste"]):
            if not F.wirkt(welt, aufbau, tasten.codes(n)):
                tot.append("%s (%s → %s)" % (n, e["taste"], e["aktion"]))
    assert not tot, "%s/%s: in der tabelle, tut aber nichts: %s" % (name, ansicht, tot)
