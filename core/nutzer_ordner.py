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
    w = wurzel()
    echt = os.path.realpath(_kandidat(pfad, w, standard))
    return echt if im_unterordner(echt, erlaubt) else None


def _kandidat(pfad, w: str, standard: str) -> str:
    roh = os.path.expanduser(str(pfad or "").strip())
    if os.path.isabs(roh):
        return roh
    teile = roh.replace("\\", "/").strip("/").split("/")
    oben = next((u for u in UNTERORDNER if teile and teile[0].lower() == u.lower()), None)
    if oben:
        return os.path.join(w, oben, *teile[1:])
    return os.path.join(w, standard, roh)


def pfad(roh, standard: str = INPUT) -> str:
    """Wie `aufloesen`, aber ohne Prüfung und ohne Ordner anzulegen: der
    absolute Pfad, den ein Name meint („x.md" → Input/x.md). Ob er drin
    liegt, entscheidet der Aufrufer (context.erlaubt, 2026-10-09)."""
    return os.path.abspath(_kandidat(roh, wurzel(anlegen=False), standard))


def im_unterordner(abs_pfad: str, erlaubt=UNTERORDNER) -> bool:
    """Liegt der Pfad (Verweise aufgelöst) in einem der Unterordner?"""
    echt = os.path.realpath(abs_pfad)
    w = wurzel(anlegen=False)
    return any(_drin(echt, os.path.join(w, u)) for u in erlaubt)


def anzeige(abs_pfad: str) -> str:
    """Wie ein Pfad genannt wird: relativ zum Nutzerordner („Input/x.zip")."""
    w = wurzel(anlegen=False)
    return os.path.relpath(abs_pfad, w) if _drin(abs_pfad, w) else abs_pfad


def ist_drin(abs_pfad: str) -> bool:
    """Liegt der (echte) Pfad im Nutzerordner?"""
    return _drin(os.path.realpath(abs_pfad), wurzel(anlegen=False))
