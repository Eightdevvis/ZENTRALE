#!/usr/bin/env python3
# scripts/open_tutor_room.py
#
# Der Hub startet die App „tutor": Stimm-Dienste, Tutor-Server, Zimmer.
#
# Seit 2026-10-09 ist der Sprach-Tutor eine eigene App (Repo language-tutor,
# memory/system/hub_bauplan.md). Dieser Starter ist das „App starten" des Hubs:
#
#   1. App finden (siehe app_ordner) und ihr Manifest app.toml lesen.
#   2. Läuft der Tutor-Server auf DIESEM Rechner: Stimm-Dienste (Whisper :5050,
#      TTS :5051) und den Server selbst hochfahren, falls sie nicht schon laufen.
#   3. Das Zimmer (laut Manifest) öffnen und warten, bis es zugeht.
#   4. Nur abräumen, was dieser Starter selbst gestartet hat (am PC laufen die
#      Dienste als systemd-Units und bleiben unangetastet).
#
# Warum Dienste beim Öffnen hoch und beim Schließen wieder runter: 0RAMMachine
# (Laptop) hat kaum RAM; die Modelle dürfen dort nicht ab Boot mitlaufen.
#
# Läuft auch auf dem Pi (Aussenposten): dort gibt es kein core/, das Zimmer
# kommt im Paket unter apps/tutor/ mit, und Server + Dienste laufen am PC.
# Darum nur Standardbibliothek und kein Import aus core/.
#
# Aufruf:
#   open_tutor_room.py [--url <tutor-server>] [--hub <zentrale>] [--pruefen] [Zimmer-Argumente …]
#     --url      Adresse des Tutor-Servers. Ohne: TUTOR_URL; sonst, wenn --hub
#                auf einen anderen Rechner zeigt, derselbe Rechner mit dem
#                Port aus dem Manifest; sonst die Adresse aus dem Manifest.
#     --hub      Adresse von ZENTRALE (für die TUI, die das Zimmer per Alt+Z öffnet)
#     --pruefen  nur prüfen, ob die App da ist (Ausgabe = Satz für Sasha, Code 2)
# Env:
#   ZENTRALE_APP_PFAD_TUTOR   Ordner der App (sonst apps/tutor, sonst ../language-tutor)
#   WHISPER_MODEL             default 'base'
#   ZENTRALE_TUTOR_AUDIO=0    Audio-Dienste ganz aus

import os
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

try:
    import tomllib
except ImportError:          # Python < 3.11 (alter Pi): Manifest-Standardwerte
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (port, service-datei, label, zusatz-env) — die zwei Stimm-Dienste des Hubs.
SERVICES = [
    (5050, "whisper_service.py", "whisper",
     {"WHISPER_MODEL": os.environ.get("WHISPER_MODEL", "base")}),
    (5051, "tts_service.py", "tts", {}),
]

# Was gilt, wenn das Manifest nicht lesbar ist (alter Pi ohne tomllib).
MANIFEST_STANDARD = {"name": "tutor", "start": "python -m tutor.server",
                     "adresse": "http://127.0.0.1:5070",
                     "ansicht": {"fenster": {"start": "python tutor/room.py"}}}


def _python(ordner):
    """venv der App, sonst das von ZENTRALE (PC/Laptop 'venv', Pi '.venv'),
    sonst dieser Python."""
    for basis in (ordner, ROOT):
        for name in ("venv", ".venv"):
            kandidat = os.path.join(basis, name, "bin", "python")
            if os.path.exists(kandidat):
                return kandidat
    return sys.executable


def app_ordner():
    """Wo die App liegt. Reihenfolge: Env, Einstellung von ZENTRALE (falls
    core/ da ist), Aussenposten-Paket (apps/tutor), Nachbar-Repo."""
    kandidaten = [os.environ.get("ZENTRALE_APP_PFAD_TUTOR")]
    try:
        sys.path.insert(0, os.path.join(ROOT, "core"))
        import apps                                   # nur am PC/Laptop da
        kandidaten.append(apps.pfad("tutor"))
    except Exception:
        pass
    kandidaten += [os.path.join(ROOT, "apps", "tutor"),
                   os.path.join(ROOT, "..", "language-tutor")]
    for k in kandidaten:
        if k and os.path.isdir(os.path.join(k, "tutor")):
            return os.path.abspath(k)
    return None


def manifest(ordner):
    datei = os.path.join(ordner, "app.toml")
    if tomllib is None or not os.path.exists(datei):
        return dict(MANIFEST_STANDARD)
    with open(datei, "rb") as f:
        return tomllib.load(f)


def _befehl(ordner, start):
    teile = str(start).split()
    if teile and teile[0] == "python":
        teile[0] = _python(ordner)
    return teile


def _lokal(url):
    return (urlparse(url).hostname or "") in ("localhost", "127.0.0.1", "::1", "")


def _port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _lebt(url):
    try:
        urllib.request.urlopen(url.rstrip("/") + "/hub/gesund", timeout=1.5).read()
        return True
    except Exception:
        return False


def server_url(m, hub, gegeben):
    """Welche Adresse hat der Tutor-Server? (siehe Kopf: --url)"""
    if gegeben:
        return gegeben
    if os.environ.get("TUTOR_URL"):
        return os.environ["TUTOR_URL"]
    adresse = m.get("adresse") or MANIFEST_STANDARD["adresse"]
    if hub and not _lokal(hub):
        port = urlparse(adresse).port or 5070
        return "http://%s:%d" % (urlparse(hub).hostname, port)
    return adresse


def _start_services():
    """Fehlende Stimm-Dienste starten → [(proc, port, label, logf)] (nur eigene)."""
    if os.environ.get("ZENTRALE_TUTOR_AUDIO") == "0":
        return []
    started = []
    for port, svc, label, extra_env in SERVICES:
        skript = os.path.join(ROOT, "services", svc)
        if _port_open(port) or not os.path.exists(skript):
            continue
        logf = open(f"/tmp/zentrale-{label}.log", "a", encoding="utf-8")
        print(f"[{label}] starte (:{port}) ...", flush=True)
        proc = subprocess.Popen([_python(ROOT), skript], stdout=logf,
                                stderr=subprocess.STDOUT,
                                env=dict(os.environ, **extra_env))
        started.append((proc, port, label, logf))
    return started


def _start_server(ordner, m, url):
    """Tutor-Server starten, falls er auf dieser Adresse nicht schon lebt."""
    if _lebt(url):
        return []
    logf = open("/tmp/language-tutor-server.log", "a", encoding="utf-8")
    print("[tutor] starte den Tutor-Server ...", flush=True)
    proc = subprocess.Popen(_befehl(ordner, m.get("start") or MANIFEST_STANDARD["start"]),
                            cwd=ordner, stdout=logf, stderr=subprocess.STDOUT)
    for _ in range(40):                      # bis zu ~10 s auf den Server warten
        if _lebt(url) or proc.poll() is not None:
            break
        time.sleep(0.25)
    return [(proc, 0, "tutor-server", logf)]


def _abraeumen(started):
    for proc, _port, label, _logf in started:
        if proc.poll() is None:
            print(f"[{label}] stoppe — Zimmer zu", flush=True)
            proc.terminate()
    frist = time.time() + 5
    for proc, _port, _label, logf in started:
        try:
            proc.wait(timeout=max(0.1, frist - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            logf.close()
        except Exception:
            pass


def _argumente(argv):
    """--url/--hub/--pruefen herausnehmen, der Rest geht ans Zimmer."""
    url = hub = None
    pruefen = False
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--url", "--hub") and i + 1 < len(argv):
            if a == "--url":
                url = argv[i + 1]
            else:
                hub = argv[i + 1]
            i += 2
            continue
        if a.startswith("--url="):
            url = a.split("=", 1)[1]
        elif a.startswith("--hub="):
            hub = a.split("=", 1)[1]
        elif a == "--pruefen":
            pruefen = True
        else:
            rest.append(a)
        i += 1
    return url, hub or os.environ.get("ZENTRALE_URL"), pruefen, rest


def main(argv=None):
    url, hub, pruefen, rest = _argumente(sys.argv[1:] if argv is None else argv)
    ordner = app_ordner()
    if ordner is None:
        print("Der Sprach-Tutor ist auf diesem Rechner nicht installiert "
              "(der Ordner language-tutor fehlt neben ZENTRALE).")
        return 2
    m = manifest(ordner)
    fenster = ((m.get("ansicht") or {}).get("fenster") or {}).get("start")
    if not fenster:
        print("Der Sprach-Tutor hat kein Fenster (app.toml ohne ansicht.fenster).")
        return 2
    if pruefen:
        return 0

    # Übergang (2026-10-09): ältere Aufrufe (Pi-Autostart vor dem Umzug)
    # geben mit --url noch die Adresse von ZENTRALE mit. Zeigt --url nicht
    # auf den Port des Tutor-Servers, ist sie als Hub gemeint.
    port = urlparse(m.get("adresse") or MANIFEST_STANDARD["adresse"]).port or 5070
    if url and urlparse(url).port != port:
        hub, url = hub or url, None
    url = server_url(m, hub, url)
    started = []
    if _lokal(url):
        # Dienste im Hintergrund hochfahren und das Fenster SOFORT öffnen —
        # nicht auf die Stimm-Modelle warten (das Zimmer wartet selbst).
        started = _start_services() + _start_server(ordner, m, url)
    env = dict(os.environ, TUTOR_URL=url,
               ZENTRALE_TUI=os.path.join(ROOT, "tui", "zentrale_tui.py"))
    if hub:
        env["ZENTRALE_URL"] = hub
    try:
        rc = subprocess.call(_befehl(ordner, fenster) + ["--url", url] + rest,
                             cwd=ordner, env=env)
    except KeyboardInterrupt:
        rc = 0
    finally:
        _abraeumen(started)
    return rc


if __name__ == "__main__":
    sys.exit(main())
