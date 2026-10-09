# core/werkzeug_nutzer_ordner.py
#
# Die Einträge von find_files, search_files und import_skill und die Frage an
# Sasha. werkzeug_register hängt EINTRAEGE hinten an seine Liste und gibt
# list_files auf gross ein Feld `ordner` (LIST_FILES_GROSS hier); ausgeführt
# wird in core/ki_nutzer_ordner.py.
#
# 2026-10-09, Gespräch 20261009-155510: Sasha legte „Chefkoch ai-v1.zip" ab
# und bat, den Skill zu importieren. list_files war bei 300 von 5.000 Dateien
# gekappt, die KI sah die Zip nicht, sagte „liegt das wirklich im richtigen
# Ordner?" — und übernehmen hätte sie ihn ohnehin nicht können. Sasha danach:
# Dateien findet man nicht durch Listen, sondern durch Suchen; und der
# Assistent arbeitet nur noch in seinem Nutzerordner (Input/, Output/,
# core/nutzer_ordner.py), nicht im Code unter ~/codicus.
#
# Nur gross (klein=None): das lokale qwen ist darauf nicht gemessen.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import skill_import
from werkzeug_eintrag import Werkzeug


def _frage_import(args: dict) -> str:
    """Sasha sieht, WELCHER Skill aus WELCHER Datei — vorab ausgepackt und
    geprüft (skill_import.vorschau), nicht aus den Argumenten geraten."""
    datei, namen = skill_import.vorschau(args.get("pfad"))
    if not namen:
        return (f"Skill aus „{datei}“ übernehmen? (Vorab war darin kein gültiger "
                f"Skill zu lesen — beim Übernehmen kommt der genaue Grund.)")
    wort = "Skill" if len(namen) == 1 else "Skills"
    liste = ", ".join(f"„{n}“" for n in namen)
    return (f"{wort} {liste} aus „{datei}“ übernehmen? Danach aktiv und in "
            f"meiner Skill-Liste; überschrieben wird nichts.")


_ORDNER = {"type": "string",
           "description": "Optional: Input, Output oder ein Ordner darin; ohne: beide."}

# list_files auf gross (gross_parameter, nur ergänzt — klein bleibt byte-gleich).
LIST_FILES_GROSS_TEXT = ("Zeigt EINEN Ordner in Sashas Nutzerordner, wie ls: "
                         "Input (Standard, was er dir gibt) oder Output (was du ihm gibst).")
LIST_FILES_GROSS_PARAMETER = {
    "type": "object",
    "properties": {"ordner": {"type": "string",
                              "description": "Input, Output oder ein Ordner darin."}},
}

EINTRAEGE = [
    Werkzeug(
        name="find_files",
        gross=("Sucht Dateien/Ordner nach Namen in Input/ und Output/, wie find: "
               "'*.zip', '*chefkoch*' oder ein Namensteil (Groß/Klein egal). Sagt, "
               "ob die Suche vollständig war."),
        parameter={
            "type": "object",
            "properties": {
                "muster": {"type": "string", "description": "Name oder Muster mit * und ?."},
                "ordner": _ORDNER,
            },
            "required": ["muster"],
        },
    ),
    Werkzeug(
        name="search_files",
        gross=("Sucht Text IN Dateien in Input/ und Output/, wie grep (Groß/Klein "
               "egal): Treffer als pfad:zeile: auszug. Sagt, ob vollständig."),
        parameter={
            "type": "object",
            "properties": {
                "text":   {"type": "string", "description": "Gesuchter Text, wörtlich."},
                "ordner": _ORDNER,
                "muster": {"type": "string", "description": "Optional: nur Dateien wie '*.md'."},
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
        gross=("Übernimmt Claude-Skills aus einer .zip oder einem Ordner in Input/ "
               "(Plugin oder Ordner mit SKILL.md), aktiv. Wird bestätigt; einen "
               "vorhandenen Namen überschreibt es nie."),
        parameter={
            "type": "object",
            "properties": {
                "pfad": {"type": "string",
                         "description": "Pfad in Input/, z. B. 'Chefkoch.zip'."},
            },
            "required": ["pfad"],
        },
    ),
]
