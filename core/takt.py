# core/takt.py
#
# Der Takt: wann ZENTRALE von sich aus etwas sagt.
#
# ── Warum es diese Schicht gibt ───────────────────────────────────────
# Bis zum 18.08.2026 war das Erinnern an Termine ein Nebeneffekt des
# Prompts: der Kalender-Block stand im Kopf, die Uhr stand daneben, und das
# Modell rechnete bei JEDEM Turn nach, wie lange es noch hin ist — "in 16
# Minuten", "noch 3 Minuten", obwohl Sasha den Termin laengst gesehen
# hatte. Es erinnerte also genau dann, wenn er ohnehin gerade schrieb, und
# nie, wenn er weg war. Das ist die falsche Richtung.
#
# Sashas Schnitt: die Uhr raus aus dem Prompt (sie holt sie mit read_time,
# wenn sie sie braucht), und das Erinnern in den CODE. Eine Prompt-Regel
# ist eine Bitte; ein Anstoss aus dem Code ist eine Tatsache.
#
# ── Was hier NICHT passiert ───────────────────────────────────────────
# Kein Modell-Aufruf, kein Netz, keine Nebenwirkung. Diese Datei sagt nur,
# OB und WOMIT angestossen werden soll — damit sie vollstaendig testbar
# bleibt und ein Fehler in der Anstoss-Logik nicht erst auffaellt, wenn er
# Geld gekostet hat. Der Treiber (ui/app.py) fragt und fuehrt aus.
#
# ── Die eigentliche Gefahr ────────────────────────────────────────────
# Nicht, dass ein Anstoss ausbleibt — dass zu viele kommen. Ein Assistent,
# der dreimal mahnt, wird abgeschaltet. Deshalb sind die Schweigeregeln
# hier hart verdrahtet und nicht dem Modell ueberlassen:
#
#   * Nachtruhe: zwischen RUHE_VON und RUHE_BIS wird nicht gesprochen.
#   * Mindestabstand: zwischen zwei Anstoessen liegen MIN_ABSTAND Minuten.
#   * Jeder Anstoss genau EINMAL — ueberlebt einen Neustart, weil der
#     Tageszustand auf der Platte liegt.

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', 'data', 'takt')
_lock = threading.Lock()

# Abstaende (in Minuten vor dem Termin), bei denen angestossen wird.
# Sashas Vorgabe: "wenn etwas noch ne stunde, ne halbe entfernt ist".
SCHWELLEN = (60, 30)

# Wie weit ein Anstoss hinter seiner Schwelle noch nachgeholt werden darf.
# Ohne dieses Fenster wuerde ein Anstoss verpasst, sobald der Treiber mal
# eine Minute spaeter dran ist oder der Rechner kurz schlief. Mit einem zu
# GROSSEN Fenster kaeme die 60-Minuten-Mahnung noch bei 40 Minuten an und
# damit direkt vor der 30er — deshalb knapp.
NACHLAUF = 5

RUHE_VON, RUHE_BIS = 22, 7      # Stunden; 22:00–06:59 wird geschwiegen
MIN_ABSTAND = 20                # Minuten zwischen zwei Anstoessen


# ── Tageszustand ──────────────────────────────────────────────────────

def _pfad(tag: date) -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return os.path.join(_DATA_DIR, f"{tag.isoformat()}.json")


def zustand(tag: date | None = None) -> dict:
    """Was heute schon gelaufen ist. Faellt auf leer zurueck.

    Auf der Platte, nicht im Speicher: ein Neustart des Backends darf nicht
    dazu fuehren, dass Sasha dieselbe Mahnung ein zweites Mal bekommt.
    """
    tag = tag or date.today()
    try:
        with open(_pfad(tag), encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _schreiben(z: dict, tag: date | None = None) -> None:
    tag = tag or date.today()
    try:
        with open(_pfad(tag), 'w', encoding='utf-8') as f:
            json.dump(z, f, ensure_ascii=False, indent=1)
    except Exception:
        pass          # ein kaputter Tageszustand darf den Chat nicht stoppen


def merken(marke: str, jetzt: datetime | None = None) -> None:
    """Einen erledigten Anstoss festhalten."""
    jetzt = jetzt or datetime.now()
    with _lock:
        z = zustand(jetzt.date())
        z.setdefault("erledigt", []).append(marke)
        z["zuletzt"] = jetzt.strftime("%H:%M")
        _schreiben(z, jetzt.date())


# ── Schweigeregeln ────────────────────────────────────────────────────

def _nachtruhe(jetzt: datetime) -> bool:
    if RUHE_VON > RUHE_BIS:          # Fenster ueber Mitternacht
        return jetzt.hour >= RUHE_VON or jetzt.hour < RUHE_BIS
    return RUHE_VON <= jetzt.hour < RUHE_BIS


def _zu_frueh(jetzt: datetime, z: dict) -> bool:
    """Mindestabstand zum letzten Anstoss."""
    letzte = z.get("zuletzt")
    if not letzte:
        return False
    try:
        h, m = (int(x) for x in letzte.split(":"))
    except Exception:
        return False
    return (jetzt.hour * 60 + jetzt.minute) - (h * 60 + m) < MIN_ABSTAND


# ── Der Anstoss ───────────────────────────────────────────────────────

def faellig(jetzt: datetime | None = None) -> dict | None:
    """Hoechstens EIN Anstoss. -> {"marke", "auftrag"} oder None.

    `auftrag` ist ein Satz in Worten, keine fertige Nachricht: was gesagt
    wird, formuliert das Modell — es kennt den Verlauf und weiss, ob Sasha
    gerade mitten in etwas steckt. Der Code entscheidet nur das WANN.
    """
    jetzt = jetzt or datetime.now()
    if _nachtruhe(jetzt):
        return None
    z = zustand(jetzt.date())
    if _zu_frueh(jetzt, z):
        return None
    erledigt = set(z.get("erledigt") or [])

    try:
        import kalender
        n = kalender.naechster_termin(jetzt)
    except Exception:
        return None
    if not n or n["morgen"]:
        # Morgen ist kein Countdown-Fall: die Schwellen liegen bei einer
        # Stunde. Was der Abend vorbereiten soll, gehoert ins Schemen.
        return None

    for schwelle in SCHWELLEN:
        if not (schwelle - NACHLAUF < n["minuten"] <= schwelle):
            continue
        marke = f"termin:{n['label']}:{n['time']}:{schwelle}"
        if marke in erledigt:
            continue
        return {
            "marke": marke,
            "auftrag": (
                f"Erinnere Sasha kurz daran, dass \"{n['label']}\" um "
                f"{n['time']} anfaengt, also in etwa {schwelle} Minuten. "
                f"Ein Satz, beilaeufig, kein Countdown und keine Nachfrage "
                f"— er hat es vermutlich auf dem Schirm. Wenn du weisst, "
                f"dass er hinfahren muss, denk an die Wegzeit."
            ),
        }
    return None


def aufraeumen(behalten: int = 7) -> int:
    """Alte Tageszustaende loeschen. -> Anzahl entfernter Dateien.

    Sonst waechst der Ordner um eine Datei pro Tag, fuer immer, und niemand
    schaut je hinein.
    """
    if not os.path.isdir(_DATA_DIR):
        return 0
    dateien = sorted(f for f in os.listdir(_DATA_DIR) if f.endswith(".json"))
    weg = dateien[:-behalten] if behalten else dateien
    for f in weg:
        try:
            os.remove(os.path.join(_DATA_DIR, f))
        except OSError:
            pass
    return len(weg)
