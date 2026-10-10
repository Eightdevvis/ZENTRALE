# tui/bausteine/ — wiederverwendbare Teile der TUI, die keine Ansicht sind.
#
# Eine Ansicht (tui/ansichten/) ist eine App mit eigenem Zustand und eigenen
# Daten. Ein Baustein weiß nichts von einer App: er bekommt Daten herein,
# rechnet und meldet zurück, was passiert ist — speichern, laden, Backend
# fragen tut immer die Ansicht. Seit 2026-10-09 (Desk View): der Canvas soll
# auch anderen Apps dienen. Bausteine importieren nichts aus ansichten/ und
# kein curses-Zeichnen — reine Logik, ohne Terminal testbar.
# Wo was wohnt: memory/system/tui_bauplan.md.
#
# Tür zum Kern (2026-10-10): Farbwähler und Stylebox brauchen core/stil.py
# (CSS-Wörter und Prüfung, stdlib-only, Tür `tui/` in
# memory/system/bauplan_kern.md). core/ HINTEN an den Suchpfad — wie
# ansichten/basis.kern_pfad(), damit nichts aus core/ ein TUI-Modul verdeckt;
# hier noch einmal, weil ein Baustein auch ohne die Ansichten geladen wird
# (Tests, scripts/stil_probe.py).
import os as _os
import sys as _sys

_KERN = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))), "core")
if _KERN not in _sys.path:
    _sys.path.append(_KERN)
