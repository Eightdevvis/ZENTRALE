# tutor/room_zugang.py
#
# Das Zimmer schickt den Zugangsschlüssel des Backends mit
# (memory/betrieb/zugang.md, 2026-10-08) — an der Wand spricht es das
# PC-Backend übers LAN an. Eigene Datei, weil tutor/room.py ein eingefrorener
# Riese ist (memory/system/bauplan_kern.md) und nichts aus dem Projekt
# importiert: hier wird nur die EINE Umsetzung der TUI
# (tui/ansichten/zugang_klient.py, stdlib-only, liegt auch auf dem Pi) per
# Dateipfad geladen, statt sie ein zweites Mal hinzuschreiben.

import importlib.util
import os

_KLIENT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "tui", "ansichten", "zugang_klient.py")


def einrichten(url):
    """Ab jetzt trägt jede urllib-Anfrage an url den Schlüssel (falls einer
    da ist). Scheitert das Laden, läuft das Zimmer ohne weiter — es soll an
    der Tür nicht abstürzen, sondern höchstens abgewiesen werden."""
    try:
        spec = importlib.util.spec_from_file_location("zentrale_zugang_klient", _KLIENT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.einrichten(url)
    except Exception as e:                       # noqa: BLE001
        print(f"[room] Zugangsschlüssel nicht eingerichtet: {e}")
