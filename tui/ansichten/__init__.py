# tui/ansichten/ — die Teile der TUI, je Ansicht ein Modul.
#
# Bis 06.10.2026 steckte das alles als Closures in EINER Funktion (run_ui in
# tui/zentrale_tui.py, 7.700 Zeilen). Jetzt bekommt jede Ansicht ein
# Kontext-Objekt (kontext.Kontext) mit dem, was alle teilen, und trägt ihren
# eigenen Zustand selbst. Wie geschnitten ist und warum:
# memory/system/tui_bauplan.md.
#
# Hier werden alle Teile einmal geladen, damit zentrale_tui.py nur
# `ansichten` importieren muss — als Skript (tui/ im Pfad) wie als Paket
# (tui.ansichten, in den Tests) gleich.

from . import basis, farben, kontext, text  # noqa: F401
from . import chat  # noqa: F401
