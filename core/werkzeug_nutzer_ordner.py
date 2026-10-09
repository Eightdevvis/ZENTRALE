# core/werkzeug_nutzer_ordner.py
#
# Die Einträge von find_files, search_files, import_skill, unzip und
# remove_input und ihre Fragen an Sasha. werkzeug_register hängt EINTRAEGE hinten an seine Liste und gibt
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

import input_dateien
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


def ansehen(args: dict) -> bool:
    """unzip: nur den Inhalt zeigen? Modelle schicken auch „true" als Text."""
    v = args.get("ansehen")
    return v is True or str(v).strip().lower() in ("true", "1", "ja")


def _frage_unzip(args: dict) -> str:
    """Sasha sieht Ziel, Zahl und Größe — vorab aus der Zip gelesen
    (input_dateien.ansehen), nicht aus den Argumenten geraten."""
    roh = str(args.get("datei") or "").strip() or "?"
    try:
        z = input_dateien.ansehen(roh)
    except input_dateien.Fehler:
        return (f"„{roh}“ auspacken? (Vorab nicht lesbar — beim Auspacken kommt der "
                f"genaue Grund.)")
    weg = f", {len(z['ausgelassen'])} ausgelassen" if z["ausgelassen"] else ""
    return (f"„{z['datei']}“ nach {z['ziel']} auspacken? {len(z['dateien'])} Dateien, "
            f"{input_dateien.groesse(z['bytes'])}{weg}.")


def _frage_remove_input(args: dict) -> str:
    roh = str(args.get("datei") or "").strip() or "?"
    return f"„{roh}“ aus Input entfernen? (kommt in den Papierkorb)"


_DATEI = {"type": "string", "description": "Name in Input/, z. B. 'Fotos.zip'."}

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
    # unzip und remove_input (2026-10-09): Zips, die kein Skill sind, und
    # Input/ aufräumen (core/input_dateien.py, core/input_aufraeumen.py).
    Werkzeug(
        name="unzip",
        schreibt=True,
        beweis="zählt die Dateien im neuen Ordner unter Output/ nach",
        erlaubnis=lambda args: not ansehen(args),
        frage=_frage_unzip,
        alltag="zip-dateien auspacken",
        gross=("Packt eine .zip aus Input/ nach Output/<name>/ aus; wird bestätigt, "
               "überschreibt nie. ansehen=true: nur den Inhalt zeigen."),
        parameter={
            "type": "object",
            "properties": {
                "datei": _DATEI,
                "ansehen": {"type": "boolean", "description": "Nur Inhalt zeigen."},
            },
            "required": ["datei"],
        },
    ),
    Werkzeug(
        name="remove_input",
        schreibt=True,
        beweis="prüft: im Papierkorb da, in Input/ weg",
        erlaubnis=True,
        frage=_frage_remove_input,
        alltag="dateien aus input wegräumen",
        gross=("Legt eine Datei/einen Ordner aus Input/ in den Papierkorb "
               "(wird bestätigt, löscht nie)."),
        parameter={
            "type": "object",
            "properties": {"datei": _DATEI},
            "required": ["datei"],
        },
    ),
]
