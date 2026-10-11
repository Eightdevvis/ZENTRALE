# core/ablage_wache.py
#
# Schaut alle paar Sekunden in Sashas Ablage-Ordner (~/Zentrale/Ablage) und
# zieht ihn nach (core/ablage_sichtbar.abgleichen): Eingeworfenes wird ein
# Dokument, Geändertes eine neue Fassung, Gelöschtes kommt in den Papierkorb.
#
# 2026-10-11, Sasha: „den ordner wo ich sachen direkt reinschmeißen kann
# direkt nachrüsten". Nachsehen statt Datei-Ereignisse (inotify): läuft auf
# jedem Rechner gleich, braucht kein Paket, und ein halb kopierter Download
# fällt über die zwei Blicke mit gleicher Größe ohnehin heraus.
#
# Einstellung `ablage_wache` (an|aus, Standard an). Gestartet von
# ui/app.py:start_ui() neben dem Takt.
#
# Ablauf (Schicht 4, memory/system/bauplan_kern.md).

import threading
import time

import ablage_sichtbar
import ai_config
import state

TICK = 3.0          # Sekunden zwischen zwei Blicken


def an() -> bool:
    wert = str(ai_config.setting("ablage_wache", "an") or "an").strip().lower()
    return wert not in ("aus", "0", "false", "nein", "off")


def einmal() -> dict:
    """Ein Blick; Neues kommt ins Log (die TUI zeigt es über /api/ablage)."""
    bericht = ablage_sichtbar.abgleichen()
    for doc_id in bericht["neu"]:
        state.push_log(f"ABLAGE: neu eingeworfen {doc_id}")
    for doc_id in bericht["entfernt"]:
        state.push_log(f"ABLAGE: von Sasha entfernt {doc_id} (im Papierkorb)")
    return bericht


def starten() -> None:
    if not an():
        state.push_log("ABLAGE-WACHE: aus (Einstellung ablage_wache)")
        return

    def _run():
        while True:
            try:
                einmal()
            except Exception as e:      # noqa: BLE001 — die Wache läuft weiter
                state.push_log(f"ABLAGE-WACHE: {type(e).__name__}: {e}")
            time.sleep(TICK)

    threading.Thread(target=_run, daemon=True, name="ablage-wache").start()
