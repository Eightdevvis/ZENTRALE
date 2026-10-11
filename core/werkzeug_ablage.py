# core/werkzeug_ablage.py
#
# Die Ablage als Quelle des Werkzeug-Erzeugers (core/werkzeug_erzeuger/):
# replace_document, trash_document, restore_document. Hier nur die
# Aktions-Schemas (MCP-Form + x-zentrale) und das Gate; was eine Aktion TUT,
# steht im Adapter (core/ki_ablage_adapter.py).
#
# 2026-10-11 (Führerschein-Gespräch: jede Änderung eines PDFs wurde eine
# weitere Kopie). Entscheidungen:
#   - Über den Erzeuger statt von Hand: Schema-Prüfung, Nachlesen per id,
#     Rücknahme und Satzform kommen aus der einen Schutzschicht.
#   - Das Gate hängt am Dokument, nicht am Werkzeug (Sasha: „ihre eigenen
#     dokumente soll sie einfach so wegräumen können. meine sachen soll sie
#     mit nachfrage wegräumen können"): gehört es der KI, kein Ja; gehört es
#     Sasha (im Zweifel), jedes Mal ein eigenes Ja — nur „ja, nur dieses mal"
#     und „nein", kein „immer". Der Erzeuger kennt nur „schreibend = fragen";
#     die Felder werden darum nach dem Erzeugen gesetzt (unten).
#   - restore_document ist frei: es legt nur zurück, löscht nichts.
#   - Immer gebaut, unabhängig von `werkzeuge_erzeugt` (das schaltet den
#     Kalender zwischen erzeugt und handgeschrieben; die Ablage hat keinen
#     handgeschriebenen Zwilling).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import ki_ablage_adapter
import werkzeug_erzeuger

X = "x-zentrale"

_ID = {"type": "string", "description": "Dokument-id aus dem Verlauf.",
       X: {"ziel": True, "fehlt": "DOK-UNBEKANNT"}}


def _aktion(name, beschreibung, felder, pflicht, **x) -> dict:
    return {"name": name, "description": beschreibung,
            "inputSchema": {"type": "object", "properties": felder,
                            "required": list(pflicht)},
            "annotations": {"readOnlyHint": False, "destructiveHint": False},
            X: x}


AKTIONEN = [
    _aktion(
        "replace_document",
        "Ersetzt ein Dokument der Ablage durch eine neue Fassung (gleiche Art: Text, "
        "PDF, Word aus Markdown); das alte kommt in den Papierkorb. Statt Kopien daneben.",
        {"id": _ID,
         "inhalt": {"type": "string", "description": "Der ganze neue Inhalt (Markdown)."},
         "titel": {"type": "string", "description": "Optional neuer Titel."}},
        ("id", "inhalt"),
        art="anlegen", alltag="dokumente ersetzen", worte=("ersetzt", "Ersetzen"),
        beweis="liest nach: neue Fassung lesbar, das Original im Papierkorb",
        nichts="nichts ersetzt",
    ),
    _aktion(
        "trash_document",
        "Legt ein Dokument der Ablage in den Papierkorb (löscht nie).",
        {"id": _ID},
        ("id",),
        art="aendern", alltag="dokumente in den papierkorb legen",
        worte=("in den Papierkorb gelegt", "In den Papierkorb legen"),
        beweis="liest den Kopf nach: liegt im Papierkorb", nichts="nichts weggeräumt",
    ),
    _aktion(
        "restore_document",
        "Holt ein Dokument aus dem Papierkorb der Ablage zurück.",
        {"id": _ID},
        ("id",),
        art="aendern", alltag="dokumente aus dem papierkorb holen",
        worte=("zurückgeholt", "Zurückholen"),
        beweis="liest den Kopf nach: liegt nicht mehr im Papierkorb",
        nichts="nichts zurückgeholt",
    ),
]

QUELLE = werkzeug_erzeuger.Quelle(name="ablage", praefix="A", bereich="ablage",
                                  aktionen=AKTIONEN,
                                  adapter=ki_ablage_adapter.AblageAdapter())

EINTRAEGE = werkzeug_erzeuger.werkzeuge(QUELLE)

for _w in EINTRAEGE:
    if _w.name == "restore_document":
        _w.erlaubnis, _w.frage = False, None
    else:
        _w.erlaubnis = ki_ablage_adapter.gehoert_sasha
        _w.nur_einmal = lambda args: True
        _w.immer_erlaubbar = False
