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
from datetime import datetime

import kern         # der eine Einstieg in den Chat (core/kern.py)
import ai_backends  # type: ignore
import anwesenheit  # ist Sasha da? schaut er ZENTRALE an?
import gespraeche   # das Gespräch „Erinnerungen“ (core/gespraeche.py)
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

# Harte Zeitgrenze für den KI-Aufruf einer Erinnerung (Sekunden, Wanduhr).
# Anlass 19.10.2026: der Cloud-Aufruf überlebte einen Laptop-Schlaf und kam
# zwei Stunden später zurück. Länger als das wartet keine Erinnerung — dann
# geht eine kurze Meldung ohne KI raus (_kurzmeldung), sofern noch frisch.
KI_GRENZE = 90

# Die Uhr für die Frische-Prüfung. Wanduhr, nicht monotonic: die monotone
# Uhr steht im Schlaf still. Eigener Name, damit Tests den Sprung stellen.
_jetzt = datetime.now


def _kurzmeldung(anstoss):
    """Der Satz, wenn die KI nicht rechtzeitig antwortet — ohne Modell."""
    label, zeit = anstoss.get("label"), anstoss.get("time")
    if label and zeit:
        return f"„{label}“ fängt um {zeit} an."
    return "Ein Termin steht gleich an — Details im Gespräch „Erinnerungen“."


def _ki_text(history, backend):
    """Den KI-Zug fahren, höchstens KI_GRENZE Sekunden. -> Text oder None
    (None = Zeitgrenze gerissen).

    Der Stream läuft in einem eigenen Thread, weil ein hängender Netzaufruf
    sich von innen nicht abbrechen lässt. Gewartet wird gegen die Wanduhr in
    kurzen Scheiben: nach einem Schlaf ist die Frist sofort vorbei, statt
    noch einmal 90 s draufzulegen. Bei Ablauf wird das Abbruch-Signal
    gesetzt; was der Thread danach noch liefert, verfällt.
    """
    abbruch = threading.Event()
    fertig = threading.Event()
    stuecke = []

    def _lauf():
        try:
            for token in kern.chat(history, backend=backend, abbruch=abbruch):
                if abbruch.is_set():
                    break
                # Nur Text. Ein Erlaubnis-Dialog kann hier niemanden
                # erreichen — es sitzt ja niemand vor einem Stream.
                if isinstance(token, dict):
                    # Ein Fehler wird nicht zur Meldung, soll aber auch nicht
                    # spurlos verschwinden.
                    if 'fehler' in token:
                        state.push_log(f"ERINNERUNG ✗  {token['fehler']}")
                    continue
                stuecke.append(token)
        except Exception as e:
            state.push_log(f"ERINNERUNG ✗  {type(e).__name__}: {e}")
        finally:
            fertig.set()

    threading.Thread(target=_lauf, daemon=True, name="takt-ki").start()
    frist = time.time() + KI_GRENZE
    while not fertig.is_set():
        rest = frist - time.time()
        if rest <= 0:
            abbruch.set()
            state.push_log(f"ERINNERUNG ✗  KI nach {KI_GRENZE} s ohne Antwort")
            return None
        fertig.wait(min(1.0, rest))
    return "".join(stuecke).strip()


def sprechen(anstoss):
    """Einen Anstoß durch das normale KI-Backend jagen und ablegen.

    Seit 2026-10-07 (Claude-Web-Plan Phase 2) landet das im eigenen
    Gespräch „Erinnerungen", nicht mitten im Thema, an dem Sasha gerade
    sitzt. Dort steht auch der Auftrag — VERSTECKT: die TUI zeigt ihn nicht
    (er ist keine Äußerung von Sasha, er soll keine Sätze lesen, die er nie
    geschrieben hat), und die KI sieht ihn später als „automatischer
    Auftrag" gekennzeichnet (gespraeche.text_fuer_ki). So weiß sie im
    nächsten Zug, worauf ihre Erinnerung antwortete.
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
    gid = gespraeche.erinnerungen()
    history = gespraeche.verlauf_fuer_ki(gid) + [
        {"role": "user", "content": auftrag}]
    text = _ki_text(history, backend)
    ki = text is not None
    if not ki:
        # Zeitgrenze gerissen: eine kurze Meldung ohne KI statt keiner.
        text = _kurzmeldung(anstoss)
    if not text:
        return False

    # ── Frische-Prüfung, direkt vor dem Melden ────────────────────────
    # Zwischen Auslösen und hier kann ein Laptop-Schlaf liegen. Eine
    # Erinnerung an einen Termin, der schon läuft oder vorbei ist, ist
    # keine — sie landet nur noch als veraltet im Verlauf, mit Grund.
    grund = takt.veraltet(anstoss, _jetzt())
    gespraeche.anhaengen(gid, "user", auftrag, versteckt=True)
    if grund:
        gespraeche.anhaengen(gid, "assistant", text,
                             warnungen=[f"Veraltet, nicht gemeldet: {grund}"])
        state.push_log(f"ERINNERUNG veraltet: {grund}")
        return False
    gespraeche.anhaengen(gid, "assistant", text,
                         warnungen=None if ki else [
                             f"Kurzmeldung ohne KI: keine Antwort nach {KI_GRENZE} s"])
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
        state.push_log("ERINNERUNGEN: aus (ZENTRALE_TAKT=0)")
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
                state.push_log(f"ERINNERUNG: {anstoss['marke']}")
                sprechen(anstoss)
            except Exception as e:
                state.push_log(f"ERINNERUNG: {type(e).__name__}: {e}")

    threading.Thread(target=_run, daemon=True, name="takt").start()
