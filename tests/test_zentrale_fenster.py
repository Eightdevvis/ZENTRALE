"""
Der Fenster-Umschalter: eine Taste, drei Faelle.

Sasha, 20.08.2026 — zwei Fehler an einem Tag, beide an derselben Stelle:

  „wenn ich modz drücke flackert das fenster aber schließt sich nicht"
  „jetzt klebt es links oben in der ecke!"

Der erste kam davon, dass eine i3-Regel (`for_window … move scratchpad`)
das Fenster jederzeit wieder wegziehen konnte. Der zweite davon, dass
`move position center` auf den Koordinatenursprung zentriert statt auf den
Bildschirm — gemessen: x=-643, y=-390 bei 1440x900. Beides fiel vorher
nicht auf, weil das Scratchpad-Einblenden die Lage selbst gesetzt hat.

Was hier getestet wird, ist die ENTSCHEIDUNG (welcher der drei Faelle
gilt) — die laesst sich gegen nachgebaute i3-Baeume pruefen. Dass die
Platzierung sitzt, ist auf der Maschine gemessen worden: 726x679 auf
357/111 bei 1440x900, also exakt mittig, und zwar nach dem Start UND nach
dem Weglegen und Wiederholen.
"""

import importlib.util
import os
import stat
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFAD = os.path.join(ROOT, "scripts", "zentrale-fenster")


@pytest.fixture(scope="module")
def zf():
    """Das Skript als Modul laden — es hat keine .py-Endung."""
    spec = importlib.util.spec_from_loader(
        "zentrale_fenster",
        importlib.machinery.SourceFileLoader("zentrale_fenster", PFAD))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _fenster(rolle):
    return {"type": "con", "name": "ZENTRALE",
            "window_properties": {"window_role": rolle},
            "nodes": [], "floating_nodes": []}


def _baum(*, wo):
    """wo: 'sichtbar' | 'scratchpad' | 'nirgends'"""
    arbeit = {"type": "workspace", "name": "1", "nodes": [],
              "floating_nodes": []}
    scratch = {"type": "workspace", "name": "__i3_scratch", "nodes": [],
               "floating_nodes": []}
    if wo == "sichtbar":
        arbeit["floating_nodes"].append(_fenster("zentrale"))
    elif wo == "scratchpad":
        scratch["nodes"].append(_fenster("zentrale"))
    return {"type": "root", "name": "root",
            "nodes": [arbeit, scratch], "floating_nodes": []}


# ── Die drei Faelle ───────────────────────────────────────────────────

def test_sichtbares_fenster_wird_gefunden(zf):
    assert zf.finden(_baum(wo="sichtbar")) == (True, False, "1")


def test_weggelegtes_fenster_wird_als_weggelegt_erkannt(zf):
    """Der Kern des Flacker-Fehlers: das Fenster lag im Scratchpad,
    waehrend Sasha draufschaute. Wer das verwechselt, legt weg statt zu
    holen — und umgekehrt."""
    gefunden, im_scratchpad, _ws = zf.finden(_baum(wo="scratchpad"))
    assert (gefunden, im_scratchpad) == (True, True)


def test_kein_fenster_heisst_kein_fenster(zf):
    assert zf.finden(_baum(wo="nirgends"))[0] is False


def test_fremde_fenster_zaehlen_nicht(zf):
    """xfce4-terminal vergibt fuer jedes Fenster dieselbe KLASSE — nur die
    Rolle unterscheidet ZENTRALE von jedem anderen Terminal."""
    baum = _baum(wo="nirgends")
    baum["nodes"][0]["floating_nodes"].append(_fenster("xfce4-terminal-17870"))
    assert zf.finden(baum)[0] is False


def test_auch_tief_verschachtelt_gefunden(zf):
    """In einem echten Baum haengt das Fenster unter Ausgabe, Inhalt und
    Workspace — eine Suche, die nur eine Ebene tief schaut, findet nichts."""
    tief = {"type": "con", "name": "tief", "nodes": [], "floating_nodes": []}
    ganz_tief = {"type": "con", "name": "tiefer",
                 "nodes": [_fenster("zentrale")], "floating_nodes": []}
    tief["nodes"].append(ganz_tief)
    baum = _baum(wo="nirgends")
    baum["nodes"][0]["nodes"].append(tief)
    assert zf.finden(baum)[0] is True


# ── Die Platzierung ───────────────────────────────────────────────────

def test_groesse_und_mitte_sind_zwei_befehle(zf, monkeypatch):
    """In EINER Kette rechnet i3 die Mitte mit der alten Groesse und setzt
    das Fenster an den Rand (gemessen: x=0 statt x=357)."""
    gerufen = []
    monkeypatch.setattr(zf, "i3", lambda *a: gerufen.append(a[0]))
    zf.platzieren()
    assert any("resize set" in b for b in gerufen)
    assert any("move absolute position center" in b for b in gerufen)
    assert not any("resize set" in b and "center" in b for b in gerufen)


def test_zentriert_wird_absolut(zf, monkeypatch):
    """`move position center` allein zentriert auf den Koordinatenursprung —
    genau daran klebte das Fenster in der linken oberen Ecke."""
    gerufen = []
    monkeypatch.setattr(zf, "i3", lambda *a: gerufen.append(a[0]))
    zf.platzieren()
    mitte = [b for b in gerufen if "center" in b]
    assert mitte and all("absolute" in b for b in mitte)


def test_das_skript_macht_schwebend_ohne_die_i3_regel(zf, monkeypatch):
    """Sonst haengt das Aussehen daran, dass die Konfiguration eingebunden
    ist — und eine gekachelte ZENTRALE mitten im Layout ist das Gegenteil
    von dem, was die Taste verspricht."""
    gerufen = []
    monkeypatch.setattr(zf, "i3", lambda *a: gerufen.append(a[0]))
    zf.platzieren()
    assert any("floating enable" in b for b in gerufen)


# ── Handwerkliches ────────────────────────────────────────────────────

def test_das_skript_ist_ausfuehrbar():
    """i3 ruft es direkt auf; ohne x-Bit passiert auf $mod+z nichts."""
    assert os.stat(PFAD).st_mode & stat.S_IXUSR


def test_rolle_ist_umstellbar(zf):
    """Damit sich der Ablauf mit einem Wegwerf-Fenster pruefen laesst, ohne
    Sashas laufende ZENTRALE anzufassen."""
    quelle = open(PFAD, encoding="utf-8").read()
    assert "ZENTRALE_FENSTER_ROLLE" in quelle
