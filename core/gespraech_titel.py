# core/gespraech_titel.py
#
# Ein Gespräch bekommt einen Namen — ohne dass Sasha darauf wartet.
#
# Zwei Stufen (2026-10-07, Claude-Web-Plan Phase 2):
#   1. Sofort beim ersten Senden: die ersten Wörter der Frage. So steht in
#      der Liste nie ein leeres „neues gespräch", auch ohne Netz.
#   2. Nach der ersten Antwort, im Hintergrund: ein kurzer Titel (≤ 6 Wörter)
#      vom BILLIGEN Modell des aktiven Anbieters (core/billig.py, Kosten
#      gebucht). Nur wenn der Zug selbst über die Cloud lief: ein lokal
#      geführtes Gespräch geht für einen Titel nicht nach draußen.
# Ein von Hand gesetzter Titel wird nie überschrieben (gespraeche.umbenennen).
#
# Schicht 3: braucht billig (KI-Kern) und gespraeche (Dienst).

import threading

import billig
import gespraeche
import state

MAX_WOERTER = 6

_SYSTEM = (
    "Du gibst Chat-Gesprächen kurze Titel für eine Liste. Antworte NUR mit "
    "dem Titel: höchstens sechs Wörter, Deutsch (außer das Gespräch ist in "
    "einer anderen Sprache), keine Anführungszeichen, kein Punkt am Ende.")


def aus_woertern(text, n=MAX_WOERTER) -> str:
    """Die ersten Wörter einer Nachricht als Titel."""
    woerter = str(text or "").split()
    if not woerter:
        return "neues gespräch"
    titel = " ".join(woerter[:n])
    if len(titel) > 60:
        titel = titel[:59].rstrip() + "…"
    elif len(woerter) > n:
        titel += " …"
    return titel


def saeubern(roh) -> str:
    """Modell-Antwort → Titel: erste Zeile, ohne Anführungszeichen, ≤ 6 Wörter."""
    zeile = next((z for z in str(roh or "").splitlines() if z.strip()), "")
    zeile = zeile.strip().strip("\"'„“”«»*#").strip()
    if zeile.lower().startswith("titel:"):
        zeile = zeile[6:].strip()
    zeile = zeile.rstrip(".")
    return " ".join(zeile.split()[:MAX_WOERTER])


def vom_modell(frage, antwort) -> str:
    """Titel vom billigen Modell. Wirft bei Fehlern."""
    auszug = ("Sasha: " + str(frage)[:1500] + "\n\nAssistent: " + str(antwort)[:1500])
    roh, _mdl = billig.einmal(_SYSTEM, auszug, max_tokens=40, log="TITEL", timeout=30)
    titel = saeubern(roh)
    if not titel:
        raise ValueError("leerer Titel")
    return titel


def erster_titel(gid, frage):
    """Stufe 1: sofort, aus den ersten Wörtern — nur wenn noch keiner da ist."""
    try:
        if not gespraeche.kopf(gid).get("titel"):
            gespraeche.umbenennen(gid, aus_woertern(frage), von="woerter")
    except Exception as e:
        state.push_log(f"TITEL ✗ {e}")


def braucht_modell(gid) -> bool:
    """Steht noch der Wörter-Titel (oder keiner)? Nur dann fragt Stufe 2."""
    try:
        return gespraeche.kopf(gid).get("titel_von") in (None, "woerter")
    except Exception:
        return False


def im_hintergrund(gid, frage, antwort, cloud=True) -> threading.Thread:
    """Stufe 2 in einem Thread starten. -> der Thread (zum kurzen Warten).
    Ohne Cloud oder bei Fehler bleibt der Wörter-Titel stehen."""
    def los():
        if not cloud:
            erster_titel(gid, frage)
            return
        try:
            gespraeche.umbenennen(gid, vom_modell(frage, antwort), von="modell")
        except Exception as e:
            state.push_log(f"TITEL: bleibt bei den ersten Wörtern ({type(e).__name__})")
            erster_titel(gid, frage)

    t = threading.Thread(target=los, daemon=True, name="gespraech-titel")
    t.start()
    return t
