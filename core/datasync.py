# core/datasync.py
#
# Push-on-write: stupst nach einer ECHTEN Daten-Änderung einen Hintergrund-
# Push zum Peer an, damit der andere Knoten (PC ↔ Laptop) sofort den neuen
# Stand hat — statt erst beim nächsten manuellen Sync / Boot-Sync.
#
# WARUM hier und nicht per Datei-Watcher: der Trigger sitzt im SCHREIB-PFAD
# der Anwendung (lists._save_file, graphs._save, kalender._save_raw). Ein vom
# Sync EINGEHENDES rsync schreibt die Datei direkt auf Platte — NICHT durch
# diese Funktion. Damit löst ein empfangenes File NIE einen Gegen-Push aus →
# kein Ping-Pong. Ein Datei-Watcher hätte genau diese Schleife.
#
# Sicherheit / Robustheit:
#   - Nur aktiv, wenn ZENTRALE_AUTOPUSH=1 in der Umgebung steht (setzen die
#     Start-Skripte). In Tests / direktem Modul-Gebrauch also stumm.
#   - Fire-and-forget, abgekoppelt (start_new_session), eigener kurzer Timeout
#     im Skript. Eine Flagging-/Listen-Aktion blockiert NIE auf SSH oder einem
#     schlafenden Peer.
#   - Wirft nie: jede Ausnahme wird verschluckt (eine kaputte Sync-Umgebung
#     darf das Backend nicht stören).
#
# Der eigentliche Push (Peer-Wahl, Coalescing, --update) liegt im Skript
# `zentrale-push-data` (~/.local/bin), nicht hier — Python triggert nur.

import os
import shutil
import subprocess

_HELPER = "zentrale-push-data"


def notify_change(path=None):
    """Eine Daten-Änderung melden → ggf. Hintergrund-Push zum Peer anstoßen.

    No-op, wenn ZENTRALE_AUTOPUSH != "1" oder der Helfer nicht auf PATH ist.
    `path` ist nur informativ (aktuell ungenutzt — der Helfer pusht den ganzen
    untracked-Datensatz per rsync-Delta, das ist billig und coalesced sauber).
    """
    if os.environ.get("ZENTRALE_AUTOPUSH") != "1":
        return
    try:
        exe = shutil.which(_HELPER)
        if not exe:
            return
        subprocess.Popen(
            [exe],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # überlebt das Request-Handling, kein Zombie
        )
    except Exception:
        pass   # Sync darf das Backend nie stören
