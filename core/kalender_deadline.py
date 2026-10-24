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
#   * Soll-Zeit (seit 24.10.2026): Sasha: „KEINE DOPPELTEN deadlines im
#     kalender, ein modus, in dem man soll und muss umschalten kann". `time`
#     ist die MUSS-Zeit (die harte Abgabe); `soll_abstand` (Minuten ≤ 0,
#     optional) legt die eigene Wunsch-Abgabe davor — als Abstand, damit es
#     bei wöchentlichen Serien jede Woche stimmt. .ics: X-ZENTRALE-SOLL als
#     ISO-8601-Dauer (-P3DT18H). Alarm/Imprint nennen beide (Muss bleibt die
#     Wahrheit); die TUI schaltet die Anzeige um (Taste S).
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
# Soll höchstens 4 Wochen vor der Muss-Zeit (die TUI holt so weit voraus).
SOLL_HOECHSTENS = 28 * 24 * 60
WT = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_DAUER = re.compile(r"^(?:(\d+)\s*(?:d|t|tage?n?))?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?$",
                    re.I)


def ist_deadline(e) -> bool:
    return isinstance(e, dict) and e.get("typ") == TYP


def vorwarnung_von(e) -> int:
    """Die Vorwarnung eines Eintrags in Minuten (fehlt sie: die Vorgabe)."""
    v = e.get("vorwarnung") if isinstance(e, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else VORWARNUNG_STANDARD


def soll_von(e) -> int | None:
    """Der Soll-Abstand in Minuten (≤ 0) oder None (keine Soll-Zeit)."""
    v = e.get("soll_abstand") if isinstance(e, dict) else None
    if isinstance(v, int) and not isinstance(v, bool) and -SOLL_HOECHSTENS <= v <= 0:
        return v
    return None


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


def soll_pruefen(wert) -> int:
    """Soll-Abstand: Minuten ≤ 0 (int) oder Text „-3d18h" → Minuten.
    Positiv (nach der Muss-Zeit) → SOLL-NACH-MUSS; Murks oder weiter als
    SOLL_HOECHSTENS → SOLL-UNGUELTIG."""
    if isinstance(wert, bool):
        raise KalenderAbgelehnt("SOLL-UNGUELTIG", f"soll_abstand {wert!r}")
    if isinstance(wert, int):
        m = wert
    else:
        s = str(wert or "").strip().replace(" ", "").replace("\u2212", "-")
        vz = -1 if s.startswith("-") else 1
        m = dauer_lesen(s.lstrip("+-")) if s.lstrip("+-") else None
        if m is None:
            raise KalenderAbgelehnt("SOLL-UNGUELTIG", f"soll_abstand {wert!r}: Minuten ≤ 0 "
                                    "oder z. B. -3d18h")
        m *= vz
    if m > 0:
        raise KalenderAbgelehnt("SOLL-NACH-MUSS", f"soll_abstand {wert!r} liegt nach der Muss-Zeit")
    if m < -SOLL_HOECHSTENS:
        raise KalenderAbgelehnt("SOLL-UNGUELTIG", f"soll_abstand {wert!r}: höchstens "
                                f"{SOLL_HOECHSTENS // 1440} Tage vor der Muss-Zeit")
    return m


def soll_text(minuten: int) -> str:
    """-5400 → „-3d18h", 0 → „0m"."""
    return ("-" if minuten < 0 else "") + dauer_text(abs(minuten))


def typ_pruefen(typ) -> str:
    """„deadline" | „normal" (None/"" = normal); sonst TYP-UNBEKANNT."""
    t = (typ or NORMAL).strip().lower() if isinstance(typ, str) or typ is None else None
    if t not in TYPEN:
        raise KalenderAbgelehnt("TYP-UNBEKANNT", f"typ {typ!r}: {' oder '.join(TYPEN)}")
    return t


# ── Ein gespeichertes Objekt prüfen/setzen ─────────────────────────────
def setzen(obj: dict, typ=None, vorwarnung=None, soll_abstand=None) -> None:
    """typ/vorwarnung/soll_abstand an `obj` setzen (None = unverändert;
    soll_abstand "" = Soll-Zeit entfernen). typ normal entfernt alle drei;
    deadline ohne Vorwarnung bekommt die Vorgabe.
    Prüft NICHT, ob obj eine Deadline sein darf — das macht pruefen()."""
    if typ is not None:
        if typ_pruefen(typ) == TYP:
            obj["typ"] = TYP
            obj.setdefault("vorwarnung", VORWARNUNG_STANDARD)
        else:
            for feld in ("typ", "vorwarnung", "soll_abstand"):
                obj.pop(feld, None)
    if vorwarnung is not None:
        if not ist_deadline(obj):
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "vorwarnung gibt es nur bei typ deadline")
        obj["vorwarnung"] = vorwarnung_pruefen(vorwarnung)
    if soll_abstand is not None:
        if soll_abstand == "":
            obj.pop("soll_abstand", None)
            return
        if not ist_deadline(obj):
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "soll_abstand gibt es nur bei typ deadline")
        obj["soll_abstand"] = soll_pruefen(soll_abstand)


def pruefen(obj: dict, spanne: bool = False, phase: bool = False) -> None:
    """Darf `obj` so gespeichert werden? Nur Deadlines werden geprüft:
    Uhrzeit Pflicht, kein Ende, nicht mehrtägig, keine Phase."""
    if not ist_deadline(obj):
        for feld in ("vorwarnung", "soll_abstand"):
            if feld in obj:
                raise KalenderAbgelehnt("UNBEKANNTES-FELD", f"{feld} gibt es nur bei typ deadline")
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
    if "soll_abstand" in obj:
        obj["soll_abstand"] = soll_pruefen(obj["soll_abstand"])


def aus_extras(extras: dict, time, spanne: bool = False, phase: bool = False) -> dict:
    """Für add_entry/add_routine/add_span: `typ`/`vorwarnung`/`soll_abstand`
    aus den Zusatzfeldern geprüft übernehmen (vor dem Laden). typ
    normal/None = alle Felder weg. -> die Zusatzfelder."""
    felder = ("typ", "vorwarnung", "soll_abstand")
    if not any(f in extras for f in felder):
        return extras
    rest = {k: v for k, v in extras.items() if k not in felder}
    probe = {**rest, **({"time": time} if time else {})}
    soll = extras.get("soll_abstand")
    setzen(probe, extras.get("typ") or NORMAL, extras.get("vorwarnung"),
           None if soll in (None, "") else soll)
    pruefen(probe, spanne=spanne, phase=phase)
    if ist_deadline(probe):
        rest["typ"], rest["vorwarnung"] = TYP, probe["vorwarnung"]
        if "soll_abstand" in probe:
            rest["soll_abstand"] = probe["soll_abstand"]
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


def soll_zeitpunkt(e: dict, tag) -> datetime | None:
    """Die Soll-Zeit eines Vorkommens (Muss-Zeit + soll_abstand) oder None."""
    zp, s = zeitpunkt(e, tag), soll_von(e)
    if zp is None or s is None or not ist_deadline(e):
        return None
    return zp + timedelta(minutes=s)


def soll_anreichern(tage: dict) -> None:
    """entries_in_range-Ergebnis: an jede Deadline mit Soll `soll_zeit`
    („2026-10-27T18:00") hängen — Datum und Uhrzeit DIESES Vorkommens."""
    for tag, es in tage.items():
        for e in es:
            zp = soll_zeitpunkt(e, tag) if isinstance(e, dict) else None
            if zp is not None:
                e["soll_zeit"] = zp.strftime("%Y-%m-%dT%H:%M")


def _wann(zp: datetime, datum: bool = True) -> str:
    return f"{WT[zp.weekday()]} {zp.strftime('%d.%m. ') if datum else ''}{zp.strftime('%H:%M')}"


def soll_muss_text(e: dict, tag, datum: bool = True) -> str:
    """„Soll: Di 21.10. 18:00, Muss: Fr 24.10. 12:00" — leer ohne Soll."""
    soll, muss = soll_zeitpunkt(e, tag), zeitpunkt(e, tag)
    if soll is None or muss is None:
        return ""
    return f"Soll: {_wann(soll, datum)}, Muss: {_wann(muss, datum)}"


def im_fenster(e: dict, tag, jetzt: datetime) -> bool:
    """Liegt jetzt im Vorwarn-Fenster (Muss noch nicht vorbei)? Mit
    Soll-Zeit beginnt das Fenster die Vorwarnung vor der SOLL-Zeit (sonst
    wäre sie schon vorbei, bevor erinnert wird); es endet immer mit Muss."""
    r = rest_minuten(e, tag, jetzt)
    return r is not None and 0 <= r <= vorwarnung_von(e) - (soll_von(e) or 0)


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
    tage = (zp.date() - jetzt.date()).days
    wann = {0: "heute", 1: "morgen"}.get(tage, f"in {tage} Tagen")
    # Mit Soll-Zeit: beide nennen, Muss bleibt die harte Wahrheit (24.10.2026)
    klammer = soll_muss_text(e, tag) or _wann(zp)
    return f"Deadline {e.get('label', '?')} {wann} ({klammer})"
