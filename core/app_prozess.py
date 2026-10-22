# core/app_prozess.py
#
# Eine Prozess-App starten, prüfen, ob sie lebt, und wieder abräumen — die
# Handgriffe, die der Hub (core/app_verwaltung.py, Autostart mit dem Backend)
# und der Zimmer-Starter des Tutors (scripts/open_tutor_room.py) teilen.
# Vorher standen sie zweimal da (apps.befehl und open_tutor_room._befehl);
# seit 2026-10-22 (Hub-Grundlagen, memory/hub/hub_bauplan.md „Apps starten")
# nur noch hier.
#
# Nur Standardbibliothek und keine Imports aus core/: der Starter läuft auch
# auf dem Pi (Aussenposten-Paket), wo es kein Backend gibt.
#
# Eine App lebt, wenn GET <adresse>/hub/gesund antwortet (jede Prozess-App
# hat diese Route; der Tutor seit 2026-10-09).

import os
import subprocess
import sys
import time
import urllib.request

GESUND = "/hub/gesund"


def python_fuer(ordner: str, ersatz_ordner: str = None) -> str:
    """Der Python einer App: ihr eigenes venv, sonst das des Ersatz-Ordners
    (ZENTRALE: PC/Laptop `venv`, Pi `.venv`), sonst dieser Python."""
    for basis in (ordner, ersatz_ordner):
        if not basis:
            continue
        for name in ("venv", ".venv"):
            kandidat = os.path.join(basis, name, "bin", "python")
            if os.path.exists(kandidat):
                return kandidat
    return sys.executable


def befehl(ordner: str, start: str, ersatz_ordner: str = None) -> list:
    """Start-Befehl aus dem Manifest („python -m karte.server") als Liste;
    „python" wird zum Python der App."""
    teile = str(start).split()
    if teile and teile[0] == "python":
        teile[0] = python_fuer(ordner, ersatz_ordner)
    return teile


def lebt(adresse: str, wartezeit: float = 1.5) -> bool:
    """Antwortet die App unter dieser Adresse auf /hub/gesund?"""
    if not adresse:
        return False
    try:
        with urllib.request.urlopen(str(adresse).rstrip("/") + GESUND,
                                    timeout=wartezeit) as r:
            r.read()
        return True
    except Exception:
        return False


def starten(ordner: str, kommando: list, log_pfad: str, adresse: str = None,
            warten_s: float = 10.0, env: dict = None):
    """Prozess starten (Ausgabe ins Log, eigene Sitzung) und bis zu warten_s
    auf /hub/gesund warten. → (proc, logf). Lebt er danach nicht, entscheidet
    der Aufrufer (proc.poll() sagt, ob er schon tot ist)."""
    logf = open(log_pfad, "a", encoding="utf-8")
    proc = subprocess.Popen(kommando, cwd=ordner, stdout=logf,
                            stderr=subprocess.STDOUT, env=env,
                            start_new_session=True)
    if adresse:
        frist = time.monotonic() + warten_s
        while time.monotonic() < frist:
            if lebt(adresse, 0.5) or proc.poll() is not None:
                break
            time.sleep(0.25)
    return proc, logf


def anhalten(proc, logf=None, frist_s: float = 5.0) -> None:
    """Freundlich beenden (SIGTERM), nach frist_s hart (SIGKILL)."""
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=frist_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=frist_s)
    if logf is not None:
        try:
            logf.close()
        except Exception:
            pass
