# core/werkzeug_gedaechtnis.py
#
# Register-Einträge der Gedächtnis-Werkzeuge, die mit dem Umbau nach Themen
# (2026-10-11, memory/ki/gedaechtnis.md) dazukamen — hinten ans Register
# gehängt wie werkzeug_browser. Eigene Datei, weil core/werkzeug_register.py
# an der Riesen-Grenze steht. Ausgeführt wird in core/ki_werkzeuge.py.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from werkzeug_eintrag import Werkzeug

# Archivieren: die KI legt selbst weg, was nicht mehr stimmt — nach _archiv/,
# nie gelöscht (Abgleich ist additiv). Frei wie write_note, weil nichts
# verloren geht; Kernakten lehnt gedaechtnis.archivieren selbst ab. Nur gross.
EINTRAEGE = [Werkzeug(
    name="archive_note", schreibt=True,
    beweis="prüft, dass die Datei unter dem Namen nicht mehr liegt",
    gross=("Legt eine Gedaechtnis-Datei, die nicht mehr stimmt oder doppelt ist, "
           "ins Archiv (nichts wird geloescht). Vorher lesen; Teile, die noch "
           "gelten, erst mit write_note in die richtige Datei uebernehmen."),
    parameter={"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string", "description": "thema/name aus dem Index."},
        "thema": {"type": "string", "description": "Optional."}}},
)]
