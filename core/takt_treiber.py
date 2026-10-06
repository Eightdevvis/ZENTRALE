# core/takt_treiber.py
#
# Der Treiber des Takts: ein Thread, der jede Minute core/takt.py fragt, ob
# ZENTRALE von sich aus etwas sagen soll, und den Anstoß dann einmal durch das
# normale KI-Backend schickt.
#
# Schicht 4 (Ablauf, memory/system/bauplan_kern.md): er benutzt den KI-Kern
# (Schicht 3) und die Dienste darunter. Bis 2026-10-06 stand er in ui/app.py —
# in der Routen-Schicht, die nur HTTP übersetzen soll. Ein Thread mit eigener
# Entscheidung ist kein HTTP-Adapter.
#
# Gestartet wird er von ui/app.py:start_ui() (wie vorher), abschaltbar mit
# ZENTRALE_TAKT=0. Details: memory/system/takt.md.

import os
import threading
import time

import ai           # type: ignore
import ai_backends  # type: ignore
import anwesenheit  # ist Sasha da? schaut er ZENTRALE an?
import melden       # Desktop-Benachrichtigung (notify-send)
import state
import takt         # das WANN — rein, ohne Netz


# ── Der Takt: unaufgefordert sprechen ─────────────────────────────────
#
# Bis zum 18.08.2026 erinnerte ZENTRALE nur dann an einen Termin, wenn
# Sasha ohnehin gerade schrieb — der Kalender stand im Prompt, die Uhr
# daneben, und das Modell rechnete jedes Mal nach. Genau die falsche
# Richtung: es mahnte, wenn er da war, und schwieg, wenn er weg war.
#
# Jetzt entscheidet core/takt.py das WANN (rein, testbar, ohne Netz), und
# dieses Modul führt aus. Er ist bewusst dünn: fragen, einmal antworten
# lassen, in den Verlauf legen, merken.

TAKT_AN   = os.environ.get("ZENTRALE_TAKT", "1") == "1"
TAKT_TICK = 60          # Sekunden zwischen zwei Prüfungen


def sprechen(anstoss):
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


def starten():
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
                sprechen(anstoss)
            except Exception as e:
                state.push_log(f"TAKT: {type(e).__name__}: {e}")

    threading.Thread(target=_run, daemon=True, name="takt").start()
