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
# Hier steht nur noch: die App anlegen, die Bereiche einhängen, der Takt-
# Thread, der Start. Die Routen selbst liegen nach Bereich in ui/routen/
# (zustand, erfassung, klavier, listen, notizen, karte, kalender, ki,
# stimme, tutor, mail). Vorher standen alle 89 Routen in dieser einen Datei
# (2.400 Zeilen) — jede Änderung, egal woran, ging durch dieselbe Datei.
# Neue Routen gehören in ihren Bereich, nie zurück hierher
# (memory/system/bauplan_kern.md).
#
# ── Architektur ───────────────────────────────────────────────────────
#   TUI  ──GET /api/state──▶  routen/zustand.py  ──liest──▶  state.py
#   TUI  ──POST /api/chat──▶  routen/ki.py  ──ai_backends.chat_available()──┐
#        cloud → core/cloud.py (Anthropic) | core/cloud_openai.py       ◀──┤
#        local → core/ai.py ──▶ Ollama                                  ◀──┘
#   Die TUI (tui/zentrale_tui.py) ist die einzige Front; die Browser-Front
#   ist archiviert (memory/archive/browser_front.md). Welcher Kern denkt,
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

import threading
import time

from flask import Flask

import ai           # type: ignore
import ai_backends  # type: ignore  – wer denkt (local/cloud)
import anwesenheit  # type: ignore  – ist Sasha da? schaut er ZENTRALE an?
import melden       # type: ignore  – Desktop-Benachrichtigung (notify-send)
import state        # type: ignore
import takt         # type: ignore  – der Takt: wann sie unaufgefordert spricht

from ui import routen

app = Flask(__name__)

# Hot Reload: laufende Requests zählen, damit das Backend sich nie mitten in
# einer Antwort neu startet (core/hot_reload.py).
import hot_reload   # type: ignore
hot_reload.requests_zaehlen(app)

routen.einhaengen(app)




# ── Der Takt: unaufgefordert sprechen ─────────────────────────────────
#
# Bis zum 18.08.2026 erinnerte ZENTRALE nur dann an einen Termin, wenn
# Sasha ohnehin gerade schrieb — der Kalender stand im Prompt, die Uhr
# daneben, und das Modell rechnete jedes Mal nach. Genau die falsche
# Richtung: es mahnte, wenn er da war, und schwieg, wenn er weg war.
#
# Jetzt entscheidet core/takt.py das WANN (rein, testbar, ohne Netz), und
# dieser Thread führt aus. Er ist bewusst dünn: fragen, einmal antworten
# lassen, in den Verlauf legen, merken.

TAKT_AN   = os.environ.get("ZENTRALE_TAKT", "1") == "1"
TAKT_TICK = 60          # Sekunden zwischen zwei Prüfungen


def _takt_sprechen(anstoss):
    """Einen Anstoß durch das normale KI-Backend jagen und ablegen.

    Der Auftrag geht als letzte User-Nachricht mit, wird aber NICHT in den
    Verlauf geschrieben: er ist eine Regieanweisung, keine Äußerung von
    Sasha. Im Verlauf landet nur, was sie sagt — sonst läse er morgen
    Sätze, die er nie geschrieben hat.
    """
    # Dieselbe Frage, die auch die Chat-Endpoints stellen. Ohne sie wuerde
    # der Takt auf dem Laptop ohne Ollama und ohne Netz gegen ein Backend
    # reden, das es nicht gibt — jede Minute aufs Neue.
    backend = ai_backends.chat_available()
    if backend is None:
        return False

    # ── In WELCHE Lage hinein sie spricht ─────────────────────────────
    # Sashas Unterscheidung: schaut er ZENTRALE an, hat sie seine
    # Aufmerksamkeit sicher und kann sagen, worum es geht. Sonst muss sie
    # sie erst holen — dann ist die Nachricht eine Benachrichtigung, und
    # eine Benachrichtigung ist ein Satz, kein Absatz.
    #
    # Die Lage wird EINMAL bestimmt und dann beides damit entschieden
    # (Formulierung und Kanal). Zweimal fragen hiesse zwei i3-Abfragen und
    # die Moeglichkeit, dass sie sich widersprechen.
    lage = anwesenheit.lage()
    auftrag = anstoss["auftrag"] + "\n\n" + anwesenheit.satz(lage)
    if lage != anwesenheit.OFFEN:
        auftrag += (" Was du jetzt schreibst, erreicht ihn als kurze "
                    "Einblendung auf dem Bildschirm — EIN Satz, mehr liest "
                    "er dort nicht. Reicht das nicht, sag in dem Satz, dass "
                    "er in den Chat kommen soll, und leg das Ausfuehrliche "
                    "dort ab.")
    history = state.get_chat_history() + [
        {"role": "user", "content": auftrag}]
    if backend == ai_backends.CLOUD:
        stream = ai_backends.chat_cloud_module().chat_stream(history)
    else:
        stream = ai.chat_stream(history)

    stuecke = []
    for token in stream:
        # Nur Text. Ein Erlaubnis-Dialog kann hier niemanden erreichen —
        # es sitzt ja niemand vor einem Stream —, also wird er ignoriert
        # statt 180 Sekunden ins Leere zu warten.
        if isinstance(token, dict):
            # Ein Fehler wird nicht zur Takt-Meldung (frueher landete
            # "[Cloud-Fehler: …]" als ihre Initiative im Chat), aber er
            # soll auch nicht spurlos verschwinden.
            if 'fehler' in token:
                state.push_log(f"TAKT ✗  {token['fehler']}")
            continue
        stuecke.append(token)

    text = "".join(stuecke).strip()
    if not text:
        return False
    state.push_chat_message("assistant", text)
    state.push_event("KI meldet sich")
    # Auf den Desktop, wenn ZENTRALE nicht ohnehin vor ihm steht. Ohne das
    # endet ihre Initiative an der Fensterkante: eine Terminerinnerung, die
    # man erst nach dem Termin liest, ist keine.
    #
    # nur_wenn_versteckt=False, weil die Entscheidung schon oben gefallen
    # ist: `lage` ist die eine Wahrheit dieses Anstosses. melden noch einmal
    # selbst nachsehen zu lassen, koennte in der Sekunde dazwischen anders
    # ausgehen — und dann passt die Formulierung nicht zum Kanal.
    if lage != anwesenheit.OFFEN:
        melden.desktop(text, nur_wenn_versteckt=False)
    return True


def _takt_starten():
    if not TAKT_AN:
        state.push_log("TAKT: aus (ZENTRALE_TAKT=0)")
        return

    def _run():
        takt.aufraeumen()
        while True:
            try:
                time.sleep(TAKT_TICK)
                anstoss = takt.faellig()
                if not anstoss:
                    continue
                # ZUERST merken, dann sprechen. Andersherum würde ein
                # Absturz mitten im Modell-Aufruf denselben Anstoß beim
                # nächsten Tick wiederholen — und Doppel-Mahnungen sind
                # genau das, wogegen diese Schicht gebaut ist.
                takt.merken(anstoss["marke"])
                state.push_log(f"TAKT: {anstoss['marke']}")
                _takt_sprechen(anstoss)
            except Exception as e:
                state.push_log(f"TAKT: {type(e).__name__}: {e}")

    threading.Thread(target=_run, daemon=True, name="takt").start()


# ── Start ──────────────────────────────────────────────────────────────

def start_ui(host='0.0.0.0', port=5000):
    """
    Startet den Flask-Server. Wird von main.py als Background-Thread gestartet.

    host='0.0.0.0' = auf allen Netzwerk-Interfaces lauschen (auch Pi → Browser im LAN)
    debug=False     = kein Debug-Modus (würde Threading-Probleme machen)
    use_reloader=False = kein Auto-Reload (läuft ja als Thread, kein eigener Prozess)
    threaded=True   = jeder Request einen eigenen Worker-Thread. Ist zwar Flasks
                      Default, aber wir setzen es EXPLIZIT, weil die Erlaubnis-
                      Rückfrage zwingend darauf baut: ein /api/chat-Stream
                      blockiert in state.wait_permission(), während parallel der
                      POST /api/permission_answer durchkommen muss, um ihn zu
                      wecken. Ohne Threading → Deadlock.
    """
    _takt_starten()
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
