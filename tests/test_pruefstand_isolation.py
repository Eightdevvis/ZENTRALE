"""Der Prüfstand lenkt jeden Datenort um, den auch die Tests umlenken.

2026-10-10: Die Messung schrieb 17 Test-Sätze in Sashas echtes
data/klassifikator_beispiele/ — conftest kannte den neuen Ort, der
Prüfstand nicht. Dieser Test hält beide Listen deckungsgleich: kommt in
tests/conftest.py ein ZENTRALE_<NAME>_DIR dazu, muss der Prüfstand ihn auch
umlenken."""
import os
import re

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Orte, die der Prüfstand bewusst anders behandelt (eigene Konfig-Kopie).
AUSNAHMEN = {"AI_CONFIG"}


def _namen_conftest():
    text = open(os.path.join(WURZEL, "tests", "conftest.py"), encoding="utf-8").read()
    return set(re.findall(r'"ZENTRALE_([A-Z_]+)_DIR"', text))


def _namen_pruefstand():
    text = open(os.path.join(WURZEL, "scripts", "pruefstand_teile", "umgebung.py"),
                encoding="utf-8").read()
    return set(re.findall(r'\("([A-Z_]+)",\s*"[a-z_]+"\)', text))


def test_pruefstand_lenkt_alles_um_was_die_tests_umlenken():
    fehlt = _namen_conftest() - _namen_pruefstand() - AUSNAHMEN
    assert not fehlt, ("Der Prüfstand schreibt sonst in Sashas echte Daten: "
                       "in scripts/pruefstand_teile/umgebung.py ergänzen: "
                       + ", ".join(sorted(fehlt)))
