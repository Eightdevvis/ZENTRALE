# tui/bausteine/ — wiederverwendbare Teile der TUI, die keine Ansicht sind.
#
# Eine Ansicht (tui/ansichten/) ist eine App mit eigenem Zustand und eigenen
# Daten. Ein Baustein weiß nichts von einer App: er bekommt Daten herein,
# rechnet und meldet zurück, was passiert ist — speichern, laden, Backend
# fragen tut immer die Ansicht. Seit 2026-10-09 (Desk View): der Canvas soll
# auch anderen Apps dienen. Bausteine importieren nichts aus ansichten/ und
# kein curses-Zeichnen — reine Logik, ohne Terminal testbar.
# Wo was wohnt: memory/system/tui_bauplan.md.
