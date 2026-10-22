# core/werkzeug_nachschlagen.py
#
# Register-Einträge der Werkzeuge, die nur nachschlagen: Fehlercodes
# (explain_error), Messreihen (read_series) und — seit 2026-10-14 — die
# Werkzeug-Suche (search_tools). Die ersten beiden standen bis 2026-10-14
# wörtlich in core/werkzeug_register.py; umgezogen, weil das Register an der
# Riesen-Grenze steht (memory/system/bauplan_kern.md). Ihre Plätze in der
# Liste (= Prompt-Reihenfolge) bestimmt weiter das Register.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from werkzeug_eintrag import Werkzeug


# Fehlercodes nachschlagen (2026-10-09, core/fehlercodes.py): jeder Abbruch
# trägt einen Code; hier stehen Ursache und was zu tun ist. Hinten an, damit
# sich davor nichts verschiebt; nur gross, frei (liest nur eine Tabelle).
FEHLERCODE = Werkzeug(
    name="explain_error",
    gross=("Erklärt einen Fehlercode aus einem Werkzeug-Ergebnis („Fehler K-…: …“): "
           "Ursache und was zu tun ist."),
    parameter={"type": "object",
               "properties": {"code": {"type": "string",
                                       "description": "Der Code, z. B. K-ENDE-VOR-BEGINN."}},
               "required": ["code"]},
)


# Messreihen lesen (2026-10-09): bis dahin las die KI Schlaf, Stimmung & Co.
# per read_file aus data/<reihe>.json. Seit read_file auf gross nur noch
# Input/ und Output/ sieht (core/context.py), ist das der Weg. Nur lesen,
# frei; hinten an, nur gross.
MESSREIHEN = Werkzeug(
    name="read_series",
    gross=("Liest Messreihen (Schlaf, Stimmung, Training …): ohne series die "
           "Liste mit letztem Wert, mit series die Werte (Standard: letzte 30 Tage)."),
    parameter={"type": "object",
               "properties": {
                   "series": {"type": "string", "description": "Name der Reihe."},
                   "von": {"type": "string", "description": "YYYY-MM-DD."},
                   "bis": {"type": "string", "description": "YYYY-MM-DD, sonst heute."},
               }},
)


# ── Werkzeug-Suche (2026-10-14, memory/ki/werkzeug_suche.md) ───────────
# Nur gross, ganz hinten, ohne Gate, und nur mit der Einstellung
# werkzeug_suche = an (Feld schalter): aus, steht es nicht in schema(),
# und die Liste bleibt byte-gleich wie vorher. Die Schleife erledigt den
# Aufruf selbst (werkzeug_schleife.SELBST): ihr Ergebnis schaltet bei
# Anthropic Werkzeuge frei (tool_reference), bei OpenAI hängt der Adapter
# die Schemas an — dafür muss das Ergebnis an der Schleife vorbei zum
# Adapter, ein Ausführer gäbe nur Text zurück.
SUCHE = Werkzeug(
    name="search_tools",
    gross=(
        "Sucht unter den Werkzeugen, die noch nicht geladen sind, und lädt die "
        "passenden samt ihrer Gruppe — danach rufst du sie direkt auf. Geladen "
        "sind anfangs nur read_calendar, web_search und fetch_url; alles andere "
        "findest du hier: Termine eintragen, ändern, löschen; Routinen; Uhrzeit; "
        "Notizen und Gedächtnis; frühere Gespräche; Skills (load_skill); "
        "Rückfragen mit Knöpfen; Browser (LSF); Dateien, Ablage, PDF, Word, "
        "Excel; Mail und News; Messreihen. Ruf es, sobald du ein Werkzeug "
        "brauchst, das du nicht siehst, mit Stichworten zur Sache (z. B. 'Termin "
        "eintragen', 'Notiz merken', 'Excel Tabelle'); für Werkzeuge, die du "
        "schon siehst, nicht. Es sucht Werkzeuge, keine Inhalte: was in "
        "Kalender, Notizen oder Netz steht, liefern erst die gefundenen Werkzeuge."
    ),
    parameter={"type": "object", "properties": {
        "query": {"type": "string",
                  "description": "Stichworte zur Aufgabe, z. B. 'pdf zusammenfügen'."},
    }, "required": ["query"]},
    in_der_schleife=True,
    alltag="werkzeuge suchen",
    schalter="werkzeug_suche",
)
