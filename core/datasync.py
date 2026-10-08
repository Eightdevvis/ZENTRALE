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
import sys
import threading
import time

_HELPER = "zentrale-push-data"

# Abgleich über die Mitte (seit 2026-10-08, memory/betrieb/abgleich.md):
# steht die Einstellung `abgleich_weg` auf „mitte", stößt eine Änderung statt
# des rsync-Helfers scripts/abgleich.py an. Gedrosselt: höchstens ein Start
# pro DROSSEL Sekunden. Eine Änderung im Fenster geht nicht verloren — sie
# merkt sich einen Nachzügler, der am Ende des Fensters startet.
DROSSEL = 20.0
_SKRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts", "abgleich.py")
_drossel = {"zuletzt": float("-inf"), "nachzuegler": None}
_drossel_lock = threading.Lock()


def notify_change(path=None):
    """Eine Daten-Änderung melden → ggf. Hintergrund-Push zum Peer anstoßen.

    No-op, wenn ZENTRALE_AUTOPUSH != "1" oder der Helfer nicht auf PATH ist.
    `path` ist nur informativ (aktuell ungenutzt — der Helfer pusht den ganzen
    untracked-Datensatz per rsync-Delta, das ist billig und coalesced sauber).
    """
    if os.environ.get("ZENTRALE_AUTOPUSH") != "1":
        return
    try:
        import ai_config
        if (ai_config.setting("abgleich_weg") or "").strip().lower() == "mitte":
            abgleich_anstossen()
            return
    except Exception:
        pass
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


def _abgleich_starten():
    with _drossel_lock:
        _drossel["zuletzt"] = time.monotonic()
        _drossel["nachzuegler"] = None
    try:
        subprocess.Popen(
            [sys.executable, _SKRIPT, "jetzt", "--automatisch"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass   # der Timer holt es nach


def abgleich_anstossen():
    """Einen Abgleich über die Mitte anstoßen — sofort, oder (innerhalb der
    Drossel) einmal am Ende des Fensters. Wirft nie."""
    with _drossel_lock:
        rest = DROSSEL - (time.monotonic() - _drossel["zuletzt"])
        if rest > 0:
            if _drossel["nachzuegler"] is None:
                t = threading.Timer(rest, _abgleich_starten)
                t.daemon = True
                _drossel["nachzuegler"] = t
                t.start()
            return
    _abgleich_starten()
