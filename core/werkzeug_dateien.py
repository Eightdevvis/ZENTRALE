# core/werkzeug_dateien.py
#
# Die Datei-Werkzeuge der KI auf gross — alle über die Ablage: find_files,
# search_files, import_skill, unzip (Einträge und Fragen), dazu die
# gross-Fassung von list_files und read_file. werkzeug_register hängt
# EINTRAEGE hinten an; ausgeführt wird in core/ki_dateien.py.
#
# 2026-10-11, Sasha: „ja einfach nur die ablage dann. den ordner wo ich sachen
# direkt reinschmeißen kann direkt nachrüsten." Wie Claude Web gibt es EINEN
# Ort für Dateien: die Ablage (~/Zentrale/Ablage, core/ablage_sichtbar.py).
# Bis dahin arbeiteten diese Werkzeuge in ~/Zentrale/Input und Output
# (core/werkzeug_nutzer_ordner.py, 2026-10-09); remove_input ist in
# trash_document aufgegangen (core/werkzeug_ablage.py). Was blieb: Suchen sagen,
# wie vollständig sie waren (Prüfer „nicht da"), und import_skill/unzip fragen.
#
# Nur gross (klein=None): das lokale qwen ist darauf nicht gemessen; seine
# list_files/read_file bleiben byte-gleich (Schnappschuss).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import ablage_zip
import skill_import
from werkzeug_eintrag import Werkzeug


def _frage_import(args: dict) -> str:
    """Sasha sieht, WELCHER Skill aus WELCHER Datei — vorab ausgepackt und
    geprüft (skill_import.vorschau), nicht aus den Argumenten geraten."""
    datei, namen = skill_import.vorschau(args.get("id"))
    if not namen:
        return (f"Skill aus „{datei}“ übernehmen? (Vorab war darin kein gültiger "
                f"Skill zu lesen — beim Übernehmen kommt der genaue Grund.)")
    wort = "Skill" if len(namen) == 1 else "Skills"
    liste = ", ".join(f"„{n}“" for n in namen)
    return (f"{wort} {liste} aus „{datei}“ übernehmen? Danach aktiv und in "
            f"meiner Skill-Liste; überschrieben wird nichts.")


def ansehen(args: dict) -> bool:
    """unzip: nur den Inhalt zeigen? Modelle schicken auch „true" als Text."""
    v = args.get("ansehen")
    return v is True or str(v).strip().lower() in ("true", "1", "ja")


def _frage_unzip(args: dict) -> str:
    """Sasha sieht Zahl und Größe — vorab aus der Zip gelesen."""
    roh = str(args.get("id") or "").strip() or "?"
    try:
        z = ablage_zip.ansehen(roh)
    except ablage_zip.Fehler:
        return f"„{roh}“ auspacken? (Vorab nicht lesbar — beim Auspacken kommt der genaue Grund.)"
    weg = f", {len(z['ausgelassen'])} ausgelassen" if z["ausgelassen"] else ""
    return (f"„{z['titel']}“ auspacken? {len(z['dateien'])} Dateien "
            f"({ablage_zip.groesse(z['bytes'])}{weg}) — jede wird ein Dokument in deiner Ablage.")


def papierkorb(args: dict) -> bool:
    v = args.get("papierkorb")
    return v is True or str(v).strip().lower() in ("true", "1", "ja")


_ID = {"type": "string", "description": "Ablage-id der Zip."}
_KORB = {"type": "boolean", "description": "true: im Papierkorb suchen."}

# list_files und read_file auf gross (gross_parameter: nur ergänzt — klein
# bleibt byte-gleich).
LIST_FILES_GROSS_TEXT = ("Listet Sashas Ablage (Titel, id, Art, von wem), neueste zuerst; "
                         "papierkorb=true: was im Papierkorb liegt.")
LIST_FILES_GROSS_PARAMETER = {"type": "object", "properties": {"papierkorb": _KORB}}
READ_FILE_GROSS_TEXT = ("Liest ein Dokument der Ablage per id oder genauem Titel, auch "
                        "PDF, Word und Excel als Text (bis 30.000 Zeichen). Finden: "
                        "list_files, find_files.")
READ_FILE_GROSS_PARAMETER = {
    "type": "object",
    "properties": {"path": {"type": "string",
                            "description": "Ablage-id oder genauer Titel."}},
    "required": ["path"],
}

EINTRAEGE = [
    Werkzeug(
        name="find_files",
        gross=("Sucht Dokumente der Ablage nach Titel: '*.pdf', '*chefkoch*' oder ein "
               "Titelteil (Groß/Klein egal). Sagt, ob die Suche vollständig war."),
        parameter={
            "type": "object",
            "properties": {
                "muster": {"type": "string", "description": "Titel oder Muster mit * und ?."},
                "papierkorb": _KORB,
            },
            "required": ["muster"],
        },
    ),
    Werkzeug(
        name="search_files",
        gross=("Sucht Text IN den Dokumenten der Ablage (auch PDF/Word/Excel), wie grep: "
               "Treffer als „Titel“ (id):zeile: auszug. Sagt, ob vollständig."),
        parameter={
            "type": "object",
            "properties": {
                "text":   {"type": "string", "description": "Gesuchter Text, wörtlich."},
                "muster": {"type": "string", "description": "Optional: nur Titel wie '*.md'."},
                "papierkorb": _KORB,
            },
            "required": ["text"],
        },
    ),
    Werkzeug(
        name="import_skill",
        schreibt=True,
        beweis="liest die Skill-Liste nach: steht jeder neue Skill aktiv darin",
        erlaubnis=True,
        # Ein fremder Skill ist eine Anweisung an die KI selbst — jedes Mal
        # ein eigenes Ja (wie edit_skill), kein „immer".
        immer_erlaubbar=False,
        frage=_frage_import,
        alltag="skills aus dateien übernehmen",
        gross=("Übernimmt Claude-Skills aus einer Zip der Ablage (Plugin oder Ordner mit "
               "SKILL.md), aktiv. Wird bestätigt; einen vorhandenen Namen überschreibt es nie."),
        parameter={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Ablage-id der Zip."}},
            "required": ["id"],
        },
    ),
    Werkzeug(
        name="unzip",
        schreibt=True,
        beweis="liest die neuen Dokumente aus der Ablage nach und zählt sie",
        erlaubnis=lambda args: not ansehen(args),
        frage=_frage_unzip,
        alltag="zip-dateien auspacken",
        gross=("Packt eine Zip der Ablage aus: jede Datei wird ein Dokument (wird bestätigt). "
               "ansehen=true: nur den Inhalt zeigen."),
        parameter={
            "type": "object",
            "properties": {
                "id": _ID,
                "ansehen": {"type": "boolean", "description": "Nur Inhalt zeigen."},
            },
            "required": ["id"],
        },
    ),
]
