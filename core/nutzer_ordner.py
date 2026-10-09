# core/nutzer_ordner.py
#
# Sashas Nutzerordner für den Assistenten: EIN übersichtlicher Ort mit zwei
# Unterordnern —
#
#   Input/    was Sasha der KI hineinlegt (eine Zip mit einem Skill, ein PDF …)
#   Output/   was die KI Sasha gibt
#
# 2026-10-09, Sasha: der Assistent bekommt keinen Zugriff mehr auf den Code-
# Dschungel unter ~/codicus (das wird eine eigene Coder-App). Suchen
# (find_files, search_files), Auflisten (list_files auf gross) und
# import_skill arbeiten NUR hier. Anlass: Gespräch 20261009-155510 — die KI
# fand eine Zip im Projektbaum nicht, weil die Liste bei 300 von 5.000
# Dateien gekappt war.
#
# Einstellung `nutzer_ordner` (ai_config.setting, Env ZENTRALE_NUTZER_ORDNER),
# Standard ~/Zentrale. Die Unterordner entstehen beim ersten Zugriff. Tests
# lenken ihn per conftest in ein Wegwerf-Verzeichnis.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import os

import ai_config

STANDARD = "~/Zentrale"
INPUT = "Input"
OUTPUT = "Output"
UNTERORDNER = (INPUT, OUTPUT)


def wurzel(anlegen: bool = True) -> str:
    """Der Nutzerordner (echter Pfad). Mit `anlegen` samt Input/ und Output/."""
    roh = str(ai_config.setting("nutzer_ordner", STANDARD) or STANDARD).strip() or STANDARD
    pfad = os.path.realpath(os.path.expanduser(roh))
    if anlegen:
        for u in UNTERORDNER:
            os.makedirs(os.path.join(pfad, u), exist_ok=True)
    return pfad


def unterordner(name: str = INPUT) -> str:
    return os.path.join(wurzel(), name)


def _drin(pfad: str, ort: str) -> bool:
    return pfad == ort or pfad.startswith(ort + os.sep)


def aufloesen(pfad, erlaubt=UNTERORDNER, standard: str = INPUT) -> str | None:
    """Ein Pfad, wie die KI oder Sasha ihn nennt, → echter Pfad in einem der
    erlaubten Unterordner — oder None, wenn er hinausführt.

    „x.zip" → <standard>/x.zip; „Input/x.zip" / „Output/a/b.md" → dort;
    absolut nur, wenn er (Verweise aufgelöst) in einem erlaubten liegt."""
    roh = os.path.expanduser(str(pfad or "").strip())
    w = wurzel()
    if os.path.isabs(roh):
        kandidat = roh
    else:
        teile = roh.replace("\\", "/").strip("/").split("/")
        oben = next((u for u in UNTERORDNER if teile and teile[0].lower() == u.lower()), None)
        if oben:
            kandidat = os.path.join(w, oben, *teile[1:])
        else:
            kandidat = os.path.join(w, standard, roh)
    echt = os.path.realpath(kandidat)
    for u in erlaubt:
        if _drin(echt, os.path.join(w, u)):
            return echt
    return None


def anzeige(abs_pfad: str) -> str:
    """Wie ein Pfad genannt wird: relativ zum Nutzerordner („Input/x.zip")."""
    w = wurzel(anlegen=False)
    return os.path.relpath(abs_pfad, w) if _drin(abs_pfad, w) else abs_pfad


def ist_drin(abs_pfad: str) -> bool:
    """Liegt der (echte) Pfad im Nutzerordner?"""
    return _drin(os.path.realpath(abs_pfad), wurzel(anlegen=False))
