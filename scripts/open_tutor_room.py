#!/usr/bin/env python3
# scripts/open_tutor_room.py
#
# On-demand-Launcher für das Persona-ZIMMER (tutor/room.py) MIT den lokalen
# Audio-Diensten (Whisper-STT :5050, TTS :5051).
#
# ── Warum es diesen Wrapper gibt ────────────────────────────────────────
# 0RAMMachine (der Laptop) hat kaum RAM. Whisper- und TTS-Modelle dürfen
# deshalb NICHT ab Boot mitlaufen (kein systemd-Autostart wie am PC). Statt-
# dessen zahlen wir die RAM-Kosten NUR, solange der Tutor offen ist: dieser
# Launcher fährt die Dienste beim Öffnen des Zimmers hoch und beim Schließen
# wieder runter.
#
# Die TUI (tui/zentrale_tui.py → tutor_window) spawnt diesen Wrapper statt
# room.py direkt. Der Wrapper ist der langlebige Prozess; room.py ist sein
# Kind. Wenn das Zimmer-Fenster zugeht, räumt der Wrapper auf und beendet sich.
#
# ── Sicher überall ──────────────────────────────────────────────────────
# Der Wrapper startet einen Dienst NUR, wenn dessen Port frei ist, und stoppt
# beim Aufräumen NUR, was er SELBST gestartet hat. Am PC (Dienste laufen als
# systemd-Units) sieht er die Ports belegt, fasst nichts an und lässt sie beim
# Schließen in Ruhe. Am Laptop startet + stoppt er sie.
#
# Aufruf (wie room.py, Argumente werden durchgereicht):
#   open_tutor_room.py --url http://host:5000
#
# Env:
#   WHISPER_MODEL   default 'base' (gecacht + leichter als 'small' → 0-RAM);
#                   override möglich. Wird an den Whisper-Dienst durchgereicht.
#   ZENTRALE_TUTOR_AUDIO=0   → Audio-Management ganz aus (nur room.py öffnen).

import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# venv-Ordner heisst nicht ueberall gleich: PC/Laptop 'venv', Pi '.venv'
# (scripts/deploy_pi.sh, siehe memory/betrieb/deployment.md). Beide probieren,
# sonst faellt der Pi still auf den System-Python ohne pygame zurueck.
PY = sys.executable
for _name in ("venv", ".venv"):
    _cand = os.path.join(ROOT, _name, "bin", "python")
    if os.path.exists(_cand):
        PY = _cand
        break

# (port, service-datei, label, zusatz-env) — die zwei Audio-Dienste.
SERVICES = [
    (5050, "whisper_service.py", "whisper",
     {"WHISPER_MODEL": os.environ.get("WHISPER_MODEL", "base")}),
    (5051, "tts_service.py", "tts", {}),
]


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Lauscht auf host:port schon etwas? (schneller TCP-Connect-Test)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _backend_is_local():
    """Zeigt das Zimmer auf ein Backend auf DIESER Maschine?

    Whisper/TTS gehören zum BACKEND, nicht zum Fenster: room.py schickt Text an
    <url>/api/speak und Mikro-WAVs an <url>/api/transcribe — synthetisiert und
    erkannt wird also auf dem Backend-Host. Lokale Dienste hochzufahren ergibt
    darum nur Sinn, wenn das Backend hier läuft (Laptop-Solo). Zeigt die URL auf
    einen anderen Rechner (Pi → PC, Laptop → PC per zentrale-remote), wäre es
    verschwendeter RAM für Modelle, die niemand anspricht — auf dem Pi (1 GB)
    sogar schädlich.
    """
    url = os.environ.get("ZENTRALE_URL") or ""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--url" and i + 1 < len(argv):
            url = argv[i + 1]
        elif a.startswith("--url="):
            url = a.split("=", 1)[1]
    if not url:
        return True                      # ohne Angabe: room.py nimmt localhost
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1", "")


def _start_services():
    """Startet fehlende Audio-Dienste. Gibt die Liste der SELBST gestarteten
    Popen-Objekte zurück (nur die räumen wir später wieder ab)."""
    if os.environ.get("ZENTRALE_TUTOR_AUDIO") == "0":
        return []
    if not _backend_is_local():
        print("[audio] Backend ist remote — Whisper/TTS laufen dort, "
              "hier wird nichts gestartet", flush=True)
        return []
    started = []
    for port, svc, label, extra_env in SERVICES:
        if _port_open(port):
            print(f"[{label}] läuft schon (:{port}) — unangetastet", flush=True)
            continue
        env = dict(os.environ, **extra_env)
        logf = open(f"/tmp/zentrale-{label}.log", "a", encoding="utf-8")
        print(f"[{label}] starte (:{port}) ...", flush=True)
        proc = subprocess.Popen(
            [PY, os.path.join(ROOT, "services", svc)],
            stdout=logf, stderr=subprocess.STDOUT, env=env,
            start_new_session=False)   # Kind des Wrappers, kein detach → sauberes Abräumen
        started.append((proc, port, label, logf))
    return started


def _stop_services(started):
    """NUR die selbst gestarteten Dienste beenden (SIGTERM, dann SIGKILL)."""
    for proc, port, label, logf in started:
        if proc.poll() is None:
            print(f"[{label}] stoppe (:{port}) — Zimmer zu, RAM frei", flush=True)
            proc.terminate()
    deadline = time.time() + 5
    for proc, port, label, logf in started:
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            logf.close()
        except Exception:
            pass


def main():
    room = os.path.join(ROOT, "tutor", "room.py")
    if not os.path.exists(room):
        print("tutor/room.py fehlt", file=sys.stderr)
        return 1

    # Dienste im HINTERGRUND hochfahren (Popen blockiert nicht) und das Fenster
    # SOFORT öffnen — NICHT auf die Audio-Modelle warten. Früher blockierte
    # _wait_ready hier bis zu 12 s (Whisper+TTS laden frisch am Laptop) → das war
    # die gefühlte „Tutor braucht ewig zum Öffnen"-Verzögerung. room.py kommt mit
    # später-Audio klar (pollt tts/available nach, stumm bis bereit).
    started = _start_services()

    try:
        # room.py mit denselben Argumenten (--url …) starten und darauf warten.
        rc = subprocess.call([PY, room] + sys.argv[1:])
    except KeyboardInterrupt:
        rc = 0
    finally:
        _stop_services(started)
    return rc


if __name__ == "__main__":
    sys.exit(main())
