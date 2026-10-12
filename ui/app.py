# ui/app.py
#
# Flask-Backend für ZENTRALE — der Einstieg der Routen-Schicht.
#
# Flask ist ein minimales Python-Web-Framework. Es lauscht auf HTTP-Anfragen
# und leitet sie an die passende Python-Funktion weiter ("Routing").
#
# Dieses Modul läuft als eigener Thread neben dem Event-Loop (core/main.py).
# Die Kommunikation zwischen beiden Threads läuft ausschließlich über
# state.py (shared in-memory state, thread-safe via Lock).
#
# ── Aufbau (seit 2026-10-06) ──────────────────────────────────────────
# Hier steht nur noch: die App anlegen, die Bereiche einhängen, den Takt-
# Thread anwerfen (core/takt_treiber.py), der Start. Die Routen selbst liegen nach Bereich in ui/routen/
# (zugang, zustand, erfassung, klavier, listen, notizen, karte, kalender,
# ki, gespraeche, stimme, mail, skills, ablage, projekte, morgenblick,
# abgleich, desk, kachel, shop, werkstatt — die Liste führt
# ui/routen/__init__.py BEREICHE; tutor ist seit 2026-10-09 ausgezogen). Vorher standen alle 89 Routen in dieser einen Datei
# (2.400 Zeilen) — jede Änderung, egal woran, ging durch dieselbe Datei.
# Neue Routen gehören in ihren Bereich, nie zurück hierher
# (memory/system/bauplan_kern.md).
#
# ── Architektur ───────────────────────────────────────────────────────
#   TUI  ──GET /api/state──▶  routen/zustand.py  ──liest──▶  state.py
#   TUI  ──POST /api/chat──▶  routen/ki.py  ──kern.chat()──┐  (core/kern.py)
#        cloud → kern.cloud_modul(): core/cloud.py |       ◀──┤
#                core/cloud_openai.py                         │
#        local → core/ai.py ──▶ Ollama                     ◀──┘
#   (ai_backends.chat_available() sagt nur, WER denken darf; den Weg
#   wählt und fährt kern.chat.)
#   Die TUI (tui/zentrale_tui.py) ist die Haupt-Front; die Browser-Front
#   liegt unter /zentrale (routen/browser.py, memory/system/dashboard.md,
#   seit 2026-10-12 wieder da). Welcher Kern denkt,
#   steht in data/ai_config.json ('chat_backend', Code-Default 'auto').
# ──────────────────────────────────────────────────────────────────────

import sys
import os

# core/ auf den Python-Suchpfad legen, damit wir state, ai usw. importieren
# können (die liegen in core/, nicht in ui/). Muss VOR den Routen passieren:
# die importieren die Kern-Module beim Laden.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'core'))
# Projekt-Root ebenfalls, damit `ui.routen` auffindbar ist — auch wenn
# dieses Modul als `app` (mit ui/ im Suchpfad) geladen wird, wie in den Tests.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from flask import Flask

import takt_treiber  # type: ignore  – der Takt-Thread (core/takt_treiber.py)
import ablage_wache  # type: ignore  – schaut in ~/Zentrale/Ablage (core/ablage_wache.py)

from ui import routen

# static_folder=None: die Browser-Front bringt ihre Dateien selbst mit
# (routen/browser.py, unter /zentrale/static) — kein zweiter Weg über /static.
app = Flask(__name__, static_folder=None)

# Hot Reload: laufende Requests zählen, damit das Backend sich nie mitten in
# einer Antwort neu startet (core/hot_reload.py).
import hot_reload   # type: ignore
hot_reload.requests_zaehlen(app)

routen.einhaengen(app)


# ── Start ──────────────────────────────────────────────────────────────

def start_ui(host=None, port=5000):
    """
    Startet den Flask-Server. Wird von main.py als Background-Thread gestartet.

    host            = ZENTRALE_HOST aus der Umgebung, sonst '0.0.0.0' (alle
                      Interfaces — der PC braucht das, der Pi spricht ihn an).
                      Der Laptop setzt 127.0.0.1 in deploy/zentrale-kern.service:
                      von außen dann gar nicht erreichbar. Wer bindet wo und
                      warum: memory/betrieb/zugang.md „Wer lauscht wo".
    debug=False     = kein Debug-Modus (würde Threading-Probleme machen)
    use_reloader=False = kein Auto-Reload (läuft ja als Thread, kein eigener Prozess)
    threaded=True   = jeder Request einen eigenen Worker-Thread. Ist zwar Flasks
                      Default, aber wir setzen es EXPLIZIT, weil die Erlaubnis-
                      Rückfrage zwingend darauf baut: ein /api/chat-Stream
                      blockiert in state.wait_permission(), während parallel der
                      POST /api/permission_answer durchkommen muss, um ihn zu
                      wecken. Ohne Threading → Deadlock.
    """
    takt_treiber.starten()
    ablage_wache.starten()
    host = host or os.environ.get('ZENTRALE_HOST') or '0.0.0.0'
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
