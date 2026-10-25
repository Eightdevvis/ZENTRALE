# tui/ansichten/tasten_zaehler.py
#
# Der Sortierer der Leiste ganz unten (2026-10-25). Sasha: „mach einfach nur
# die shortcuts hin … dazu ein kleiner sortierer mit the most used shortcuts
# ganz nach vorne."
#
# Er zählt je Programm und Ansicht, welcher Eintrag der Tastentabelle wie oft
# gedrückt wurde (gezählt wird unter der Beschriftung, die die Leiste zeigt:
# k zählt für „↑↓", weil beide dieselbe Aktion haben). Die Leiste zeigt die
# Einträge danach meistgenutzt zuerst, ungenutzte in Tabellen-Reihenfolge
# dahinter. Es fällt nie ein Eintrag weg, es ändert sich nur die Reihenfolge.
#
# Dämpfung: die Reihenfolge einer Ansicht wird nur beim ÖFFNEN der Ansicht
# neu gerechnet (sobald die Leiste eine andere Ansicht zeigt als vorher).
# Solange man in ihr arbeitet, steht die Leiste still — sie hüpft nie unter
# den Fingern weg.
#
# Gespeichert wird lokal (nie im Repo), in
#   $ZENTRALE_TASTEN_ZAEHLER, sonst $XDG_STATE_HOME/zentrale/tasten_zaehler.json
#   (Standard ~/.local/state/zentrale/tasten_zaehler.json).
# Form: {"<programm>": {"<ansicht>": {"<beschriftung>": anzahl}}}.
# Geschrieben wird beim Ansichtswechsel und beim Beenden (nur wenn sich etwas
# geändert hat), atomar über eine Nachbardatei. Eine kaputte Datei wird zur
# Seite gelegt (…json.kaputt) und gemeldet, nie still überschrieben; dann
# zählt der Sortierer von vorn.

import json
import os
import sys

# ── Regler (Sasha entscheidet den Feinschliff) ────────────────────────
SORTIEREN = True          # False: Leiste in Tabellen-Reihenfolge wie früher


def pfad():
    if os.environ.get("ZENTRALE_TASTEN_ZAEHLER"):
        return os.environ["ZENTRALE_TASTEN_ZAEHLER"]
    basis = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(basis, "zentrale", "tasten_zaehler.json")


def _bereinigt(roh):
    """Nur die Teile behalten, die die Form haben; Rest fällt weg."""
    raus = {}
    if not isinstance(roh, dict):
        return None
    for prog, ansichten in roh.items():
        if not isinstance(prog, str) or not isinstance(ansichten, dict):
            continue
        for ansicht, zahlen in ansichten.items():
            if not isinstance(ansicht, str) or not isinstance(zahlen, dict):
                continue
            gut = {t: n for t, n in zahlen.items()
                   if isinstance(t, str) and isinstance(n, int)
                   and not isinstance(n, bool) and n > 0}
            if gut:
                raus.setdefault(prog, {})[ansicht] = gut
    return raus


class Zaehler:
    def __init__(self, datei=None):
        self.datei = datei or pfad()
        self.meldung = ""            # Grund, falls die Datei kaputt war
        self._z = self._laden()
        self._geaendert = False
        self._offen = None           # (programm, ansicht), die die Leiste zuletzt zeigte
        self._stand = {}             # deren Zahlen, eingefroren beim Öffnen

    # ── Datei ─────────────────────────────────────────────────────────
    def _laden(self):
        try:
            with open(self.datei, encoding="utf-8") as f:
                roh = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            return self._kaputt("nicht lesbar (%s)" % e.__class__.__name__)
        z = _bereinigt(roh)
        if z is None:
            return self._kaputt("keine Tabelle")
        return z

    def _kaputt(self, grund):
        """Nicht still verwerfen: zur Seite legen und melden."""
        self.meldung = "tasten-zähler %s, neu begonnen" % grund
        try:
            os.replace(self.datei, self.datei + ".kaputt")
        except OSError:
            pass
        print("[tasten_zaehler] %s: %s" % (self.datei, self.meldung), file=sys.stderr, flush=True)
        return {}

    def speichern(self):
        """Nur wenn sich etwas geändert hat. Wirft nie."""
        if not self._geaendert:
            return
        try:
            os.makedirs(os.path.dirname(self.datei) or ".", exist_ok=True)
            neu = self.datei + ".neu"
            with open(neu, "w", encoding="utf-8") as f:
                json.dump(self._z, f, ensure_ascii=False, sort_keys=True)
            os.replace(neu, self.datei)
            self._geaendert = False
        except OSError as e:
            print("[tasten_zaehler] speichern fehlgeschlagen: %s" % e, file=sys.stderr, flush=True)

    # ── Zählen und sortieren ─────────────────────────────────────────
    def zaehlen(self, programm, ansicht, beschriftung):
        stelle = self._z.setdefault(programm, {}).setdefault(ansicht, {})
        stelle[beschriftung] = stelle.get(beschriftung, 0) + 1
        self._geaendert = True

    def anzahl(self, programm, ansicht, beschriftung):
        return self._z.get(programm, {}).get(ansicht, {}).get(beschriftung, 0)

    def sortiert(self, programm, ansicht, eintraege):
        """[(taste, text)] meistgenutzt zuerst; Gleichstand (auch 0) behält
        die Tabellen-Reihenfolge. Die Zahlen gelten ab dem Öffnen der
        Ansicht (Dämpfung, siehe oben)."""
        if (programm, ansicht) != self._offen:
            self._offen = (programm, ansicht)
            self._stand = dict(self._z.get(programm, {}).get(ansicht, {}))
            self.speichern()
        if not SORTIEREN:
            return list(eintraege)
        return sorted(eintraege, key=lambda e: -self._stand.get(e[0], 0))
