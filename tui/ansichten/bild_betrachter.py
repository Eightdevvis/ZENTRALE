# tui/ansichten/bild_betrachter.py
#
# Ein Bild im Bildbetrachter des Rechners öffnen, auf dem die TUI läuft
# (Desk View, Taste `o` auf einem Bild, 2026-10-10). Ohne curses.
#
# Übernommen aus Sashas viscope (src/viscope/viewer.py, open_files, MIT,
# eigener Code) — als Kopie, nicht als Import: viscope ist ein eigenes
# Programm in einem eigenen venv, ZENTRALE soll nicht davon abhängen.
#
# betrachter (Einstellung `bild_betrachter`, liefert das Backend):
#   "system"   der Standard-Betrachter des Desktops (xdg-open, sonst gio;
#              auf dem Mac open)
#   <befehl>   ein Programm, z. B. "feh", "eog", "ristretto" — bekommt die
#              Datei als letztes Argument
#
# Gestartet wird abgelöst (eigene Sitzung, stdin/stdout/stderr ins Leere):
# der Betrachter darf nicht in curses schreiben und nicht mit der TUI
# sterben, und die TUI wartet nicht auf ihn.

import os
import shlex
import shutil
import subprocess
import sys
import tempfile


def befehl(dateien, betrachter="system"):
    """-> Befehlsliste. OSError mit lesbarem Grund, wenn kein Betrachter da ist."""
    if not dateien:
        raise OSError("kein bild zum öffnen")
    dateien = [str(d) for d in dateien]
    betrachter = str(betrachter or "system").strip() or "system"
    if betrachter == "system":
        if sys.platform == "darwin":
            return ["open", *dateien]
        # Eine Datei reicht: Desktop-Betrachter blättern im Ordner weiter.
        oeffner = shutil.which("xdg-open") or shutil.which("gio")
        if not oeffner:
            raise OSError("kein bildbetrachter gefunden — einstellung bild_betrachter setzen (z. B. feh)")
        if oeffner.endswith("xdg-open"):
            return [oeffner, dateien[0]]
        return [oeffner, "open", dateien[0]]
    cmd = [*shlex.split(betrachter), *dateien]
    if not shutil.which(cmd[0]):
        raise OSError("bildbetrachter %r ist nicht installiert" % cmd[0])
    return cmd


def oeffnen(dateien, betrachter="system"):
    """Betrachter starten, ohne zu warten. -> Name des gestarteten Programms."""
    cmd = befehl(dateien, betrachter)
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return os.path.basename(cmd[0])


def zwischenordner():
    """Ordner für Bilder, die erst vom Backend geholt werden mussten (TUI auf
    einem anderen Rechner). Unter dem System-tmp — wird beim Neustart leer."""
    p = os.path.join(tempfile.gettempdir(), "zentrale-bilder-%d" % os.getuid())
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p
