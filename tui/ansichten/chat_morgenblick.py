# tui/ansichten/chat_morgenblick.py
#
# `/morning` im Chat: das Backend erstellt den Morgenblick (POST
# /api/morgenblick, core/morgenblick.py), die TUI öffnet ihn im Browser.
# Eigene Datei, damit chat.py nur eine Zeile dafür braucht (2026-10-08,
# memory/werkzeuge/morgenblick.md).
#
# Geöffnet wird die Adresse des Backends (GET /api/ablage/<id>/roh), nicht
# eine Datei: unterwegs liegt die Ablage auf dem anderen Rechner. Nur mit
# grafischer Sitzung (DISPLAY/WAYLAND_DISPLAY) — sonst könnte xdg-open einen
# Text-Browser IN dieses Terminal starten und die TUI zerschießen.

import json
import os
import subprocess
import threading
import urllib.error

from .basis import BASE_URL, api_call

WARTEN_S = 120                 # mit KI dauert es einige Sekunden, ohne Netz länger


def im_browser_oeffnen(url) -> bool:
    """url im Standard-Browser öffnen, ohne auf ihn zu warten. -> geklappt?"""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        subprocess.Popen(["xdg-open", url], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        return False
    return True


def starten(chat):
    """/morning: im Hintergrund erstellen lassen, dann öffnen."""
    AI = chat.AI
    if AI.get("morgenblick_laeuft"):
        AI["msg"] = "Morgenblick wird schon erstellt …"
        return
    AI["morgenblick_laeuft"] = True
    AI["msg"] = "Morgenblick wird erstellt …"
    threading.Thread(target=_erstellen, args=(chat,), daemon=True,
                     name="morgenblick").start()


def _erstellen(chat, oeffnen=im_browser_oeffnen):
    AI, AI_LOCK = chat.AI, chat.AI_LOCK
    try:
        r = api_call("/api/morgenblick", "POST", {}, timeout=WARTEN_S)
    except urllib.error.HTTPError as e:
        grund = ""
        try:
            grund = json.loads(e.read().decode("utf-8", "replace")).get("error") or ""
        except Exception:
            pass
        _fertig(chat, "Morgenblick ging nicht: " + (grund or "fehler %s" % e.code))
        return
    except (urllib.error.URLError, OSError, ValueError):
        _fertig(chat, "keine verbindung zum backend — kein Morgenblick")
        return
    if not isinstance(r, dict) or not r.get("url"):
        _fertig(chat, "Morgenblick ging nicht: leere antwort")
        return
    text = ("im Browser geöffnet · ▤ in der Ablage" if oeffnen(BASE_URL + r["url"])
            else "▤ in der Ablage (/files) — kein Browser zum Öffnen")
    if not r.get("mit_ki"):
        text += " · ohne KI zusammengestellt"
    with AI_LOCK:
        AI["log"].append(("hinweis", "Morgenblick: " + text))
        AI["scroll"] = 0
    _fertig(chat, text)


def _fertig(chat, text):
    with chat.AI_LOCK:
        chat.AI["msg"] = text
        chat.AI["morgenblick_laeuft"] = False
