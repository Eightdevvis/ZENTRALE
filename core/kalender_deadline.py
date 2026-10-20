# core/kalender_deadline.py
#
# Termintyp „deadline" (seit 20.10.2026). Sasha: „ne deadline is ja ne ganz
# andere art von termin … die deadline soll rot leuchten in einem
# zeitfenster was man selbst vorher einstellen kann, je näher man ihr kommt".
#
# Eine Deadline ist ein ZEITPUNKT, keine belegte Zeit:
#   * Felder am Einmal-Termin bzw. an der Routine: `typ: "deadline"` und
#     `vorwarnung` (Minuten vor dem Zeitpunkt, ab denen gewarnt/geleuchtet
#     wird; Vorgabe VORWARNUNG_STANDARD). Ein normaler Termin hat kein `typ`.
#   * Immer mit Uhrzeit (`time`), nie mit Ende (`ende`), nie mehrtägig.
#   * Kollidiert nie (kalender_konflikte nimmt sie aus), macht keinen
#     Reise-Konflikt; im Vorwarn-Fenster ein Hinweis im Alarm-Kanal.
#   * .ics: X-ZENTRALE-TYP:DEADLINE, DTEND = DTSTART (Dauer 0) und die
#     Vorwarnung als Standard-VALARM (TRIGGER:-P3D) — kalender_ics_abbildung.
#
# Rein rechnend, braucht nur kalender_fehler (Ablehnungen) — kein Import-Kreis.
# Doku: memory/werkzeuge/kalender_deadline.md

import re
from datetime import date, datetime, timedelta

from kalender_fehler import KalenderAbgelehnt, uhrzeit

TYP = "deadline"
NORMAL = "normal"
TYPEN = (NORMAL, TYP)
# Regler (Sasha): Vorgabe 3 Tage; mehr als ein Jahr ist keine Vorwarnung mehr.
VORWARNUNG_STANDARD = 3 * 24 * 60
VORWARNUNG_HOECHSTENS = 366 * 24 * 60

_DAUER = re.compile(r"^(?:(\d+)\s*(?:d|t|tage?n?))?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?$",
                    re.I)


def ist_deadline(e) -> bool:
    return isinstance(e, dict) and e.get("typ") == TYP


def vorwarnung_von(e) -> int:
    """Die Vorwarnung eines Eintrags in Minuten (fehlt sie: die Vorgabe)."""
    v = e.get("vorwarnung") if isinstance(e, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else VORWARNUNG_STANDARD


# ── Dauer als Text: „3d", „12h", „1d12h", „90m" ────────────────────────
def dauer_lesen(text) -> int | None:
    """„3d" → 4320, „1d12h" → 2160, „90m"/„90" → 90; Murks → None."""
    if isinstance(text, bool):
        return None
    if isinstance(text, int):
        return text if text >= 0 else None
    s = str(text or "").strip().lower().replace(" ", "")
    if not s:
        return None
    if s.isdigit():
        return int(s)
    m = _DAUER.match(s)
    if not m or not any(m.groups()):
        return None
    d, h, mi = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi


def dauer_text(minuten: int) -> str:
    """4320 → „3d", 2160 → „1d12h", 90 → „1h30m", 0 → „0m"."""
    minuten = max(0, int(minuten))
    d, rest = divmod(minuten, 1440)
    h, m = divmod(rest, 60)
    teile = [f"{d}d"] * bool(d) + [f"{h}h"] * bool(h) + [f"{m}m"] * bool(m)
    return "".join(teile) or "0m"


def vorwarnung_pruefen(wert) -> int:
    """Minuten (int) oder Text („3d") → Minuten; sonst VORWARNUNG-UNGUELTIG."""
    m = dauer_lesen(wert)
    if m is None or m > VORWARNUNG_HOECHSTENS:
        raise KalenderAbgelehnt("VORWARNUNG-UNGUELTIG",
                                f"vorwarnung {wert!r}: Minuten oder z. B. 3d, 12h, 1d12h "
                                f"(höchstens {VORWARNUNG_HOECHSTENS // 1440} Tage)")
    return m


def typ_pruefen(typ) -> str:
    """„deadline" | „normal" (None/"" = normal); sonst TYP-UNBEKANNT."""
    t = (typ or NORMAL).strip().lower() if isinstance(typ, str) or typ is None else None
    if t not in TYPEN:
        raise KalenderAbgelehnt("TYP-UNBEKANNT", f"typ {typ!r}: {' oder '.join(TYPEN)}")
    return t


# ── Ein gespeichertes Objekt prüfen/setzen ─────────────────────────────
def setzen(obj: dict, typ=None, vorwarnung=None) -> None:
    """typ/vorwarnung an `obj` setzen (None = unverändert). typ normal
    entfernt beide Felder; deadline ohne Vorwarnung bekommt die Vorgabe.
    Prüft NICHT, ob obj eine Deadline sein darf — das macht pruefen()."""
    if typ is not None:
        if typ_pruefen(typ) == TYP:
            obj["typ"] = TYP
            obj.setdefault("vorwarnung", VORWARNUNG_STANDARD)
        else:
            obj.pop("typ", None)
            obj.pop("vorwarnung", None)
    if vorwarnung is not None:
        if not ist_deadline(obj):
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "vorwarnung gibt es nur bei typ deadline")
        obj["vorwarnung"] = vorwarnung_pruefen(vorwarnung)


def pruefen(obj: dict, spanne: bool = False, phase: bool = False) -> None:
    """Darf `obj` so gespeichert werden? Nur Deadlines werden geprüft:
    Uhrzeit Pflicht, kein Ende, nicht mehrtägig, keine Phase."""
    if not ist_deadline(obj):
        if "vorwarnung" in obj:
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "vorwarnung gibt es nur bei typ deadline")
        if "typ" in obj:
            raise KalenderAbgelehnt("TYP-UNBEKANNT", f"typ {obj['typ']!r}: {' oder '.join(TYPEN)}")
        return
    if phase:
        raise KalenderAbgelehnt("IST-PHASE", "eine Phase des Tagesrhythmus ist keine Deadline")
    if spanne or obj.get("bis"):
        raise KalenderAbgelehnt("DEADLINE-SPANNE")
    if not obj.get("time"):
        raise KalenderAbgelehnt("DEADLINE-OHNE-ZEIT")
    uhrzeit("time", obj["time"])
    if obj.get("ende"):
        raise KalenderAbgelehnt("DEADLINE-MIT-ENDE")
    obj["vorwarnung"] = vorwarnung_pruefen(obj.get("vorwarnung", VORWARNUNG_STANDARD))


def aus_extras(extras: dict, time, spanne: bool = False, phase: bool = False) -> dict:
    """Für add_entry/add_routine/add_span: `typ`/`vorwarnung` aus den
    Zusatzfeldern geprüft übernehmen (vor dem Laden). typ normal/None =
    beide Felder weg. -> die Zusatzfelder."""
    if "typ" not in extras and "vorwarnung" not in extras:
        return extras
    rest = {k: v for k, v in extras.items() if k not in ("typ", "vorwarnung")}
    probe = {**rest, **({"time": time} if time else {})}
    setzen(probe, extras.get("typ") or NORMAL, extras.get("vorwarnung"))
    pruefen(probe, spanne=spanne, phase=phase)
    if ist_deadline(probe):
        rest["typ"], rest["vorwarnung"] = TYP, probe["vorwarnung"]
    return rest


# ── Zeit bis zur Deadline ──────────────────────────────────────────────
def zeitpunkt(e: dict, tag) -> datetime | None:
    """Der Zeitpunkt eines Vorkommens (Tag ISO/date + time) oder None."""
    try:
        d = tag if isinstance(tag, date) else date.fromisoformat(tag)
        h, m = str(e.get("time") or "").split(":")
        return datetime.combine(d, datetime.min.time()) + timedelta(hours=int(h), minutes=int(m))
    except (TypeError, ValueError):
        return None


def rest_minuten(e: dict, tag, jetzt: datetime) -> int | None:
    """Minuten bis zur Deadline (negativ = überschritten)."""
    zp = zeitpunkt(e, tag)
    if zp is None:
        return None
    return int((zp - jetzt).total_seconds() // 60)


def im_fenster(e: dict, tag, jetzt: datetime) -> bool:
    """Liegt jetzt im Vorwarn-Fenster (noch nicht vorbei)?"""
    r = rest_minuten(e, tag, jetzt)
    return r is not None and 0 <= r <= vorwarnung_von(e)


def rest_text(e: dict, tag, jetzt: datetime, stunden: bool = True) -> str:
    """Für die KI, auf den Tag genau: „heute", „morgen", „in 2 Tagen",
    „überschritten"; heute mit `stunden` zusätzlich „in 3 h"/„in 20 min"
    (der Imprint nimmt es ohne, damit der gecachte Prompt-Kopf sich nur
    einmal am Tag ändert)."""
    zp = zeitpunkt(e, tag)
    if zp is None:
        return ""
    if zp <= jetzt:
        return "überschritten"
    tage = (zp.date() - jetzt.date()).days
    if tage == 0:
        if not stunden:
            return "heute"
        m = int((zp - jetzt).total_seconds() // 60)
        return f"heute, in {m} min" if m < 60 else f"heute, in {m // 60} h"
    if tage == 1:
        return "morgen"
    return f"in {tage} Tagen"


def alarm_text(e: dict, tag, jetzt: datetime) -> str:
    """„Deadline Analysis HÜ in 2 Tagen (Fr 24.10. 23:59)" — der Tagesteil
    wechselt höchstens einmal am Tag (die Alarm-id hängt am Text)."""
    zp = zeitpunkt(e, tag)
    wt = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[zp.weekday()]
    tage = (zp.date() - jetzt.date()).days
    wann = {0: "heute", 1: "morgen"}.get(tage, f"in {tage} Tagen")
    return (f"Deadline {e.get('label', '?')} {wann} "
            f"({wt} {zp.strftime('%d.%m.')} {zp.strftime('%H:%M')})")
