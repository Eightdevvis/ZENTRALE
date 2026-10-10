# core/farbrollen.py
#
# Das gemeinsame Wörterbuch der Farbrollen (Sasha, 2026-10-10: „die App
# entscheidet die BEDEUTUNG, jede Oberfläche die echte Farbe"). Eine App
# sagt nur, WAS ein Stück Text ist („heute", „leise" …); welche Farbe das
# wird, entscheidet die Oberfläche — die TUI in tui/ansichten/farben.py
# (FARBROLLEN, deckt jede Rolle ab, ein Test wacht), später Fenster und
# Handy auf ihre Art. Unbekannte Rolle → die Oberfläche nimmt „text".
#
# Neue Rolle: hier eintragen (Name + eine Zeile Bedeutung) UND in jeder
# Oberfläche abbilden — sonst wird der Test rot. Lieber wenige Rollen mit
# klarer Bedeutung als eine Farbe je Wunsch.
# Doku: memory/system/hub_bauplan.md „Farbrollen".
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

ROLLEN = {
    "text":     "gewöhnlicher Inhalt",
    "leise":    "Nebensache: Rahmen, Trennstriche, Uhrzeiten, Tage außerhalb",
    "kopf":     "Überschrift, Spalten- oder Tageskopf",
    "betont":   "soll ins Auge fallen, ohne Warnung zu sein",
    "heute":    "das Jetzt: der heutige Tag, was gerade läuft",
    "spanne":   "Ganztägiges, Mehrtägiges, ein Zeitraum",
    "mehr":     "Hinweis, dass nicht alles Platz hat („+3“)",
    "warnung":  "Achtung: Fehler, Überfälliges, Konflikt",
    "erledigt": "abgehakt oder vorbei",
}
RUECKFALL = "text"


def rolle(name):
    """Bekannte Rolle bleibt, alles andere wird RUECKFALL."""
    return name if name in ROLLEN else RUECKFALL
