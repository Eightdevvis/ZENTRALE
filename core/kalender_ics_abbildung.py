# core/kalender_ics_abbildung.py
#
# Ein Termin bzw. eine Routine aus dem Kalender-Dict  <->  VEVENT-Komponenten.
#
# Reine Übersetzung: kein Dateisystem, kein Zustand. Der vdir-Speicher
# (core/kalender_ics.py) entscheidet, WAS geschrieben wird; dieses Modul
# nur, WIE ein einzelnes Stück in iCalendar aussieht und wie es
# zurückgelesen wird. So lässt sich jede Abbildungsregel isoliert hin und
# zurück testen.
#
# Die Regeln sind mit Sasha entschieden (memory/werkzeuge/kalender_ics_bauplan.md):
#   Einmal-Termin            -> VEVENT, DTSTART/DTEND mit TZID=Europe/Berlin
#   ganztags                 -> DTSTART;VALUE=DATE
#   Spanne über Tage         -> EIN VEVENT, ganztags von..bis
#   Spanne + Zeit pro Tag    -> tägliche RRULE (COUNT) + Abweichungen mit
#                               RECURRENCE-ID in DERSELBEN Datei (gleiche UID)
#   Routine                  -> RRULE, ende -> DTEND
#   aus                      -> EXDATE + X-ZENTRALE-AUS
#   pausen                   -> EXDATEs + X-ZENTRALE-PAUSE (Notiz mit Grund)
#   absage_noetig            -> X-ZENTRALE-ABSAGE-NOETIG
#
# Das Verlust-Prinzip: ein Feld wird nur dann auf eine iCalendar-Property
# abgebildet, wenn es sich EXAKT zurücklesen lässt ("17:45" ja, "10" nein).
# Alles andere landet unverändert in X-ZENTRALE-EXTRAS und füllt beim Lesen
# die Lücken. Und zum Schluss liest jede Schreibfunktion ihr eigenes
# Ergebnis zurück und vergleicht: weicht es ab, wirft sie NichtAbbildbar,
# und der Speicher legt das Stück unverändert in die Nebendaten. Verloren
# geht so nie etwas — schlimmstenfalls sieht Google es nicht.

import base64
import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Timezone, vRecur

import kalender_regel

TZ_NAME = "Europe/Berlin"
TZ = ZoneInfo(TZ_NAME)
PRODID = "-//ZENTRALE//Kalender//DE"

ART_TERMIN, ART_SPANNE, ART_ROUTINE = "TERMIN", "SPANNE", "ROUTINE"

X_ART = "X-ZENTRALE-ART"
X_POS = "X-ZENTRALE-POS"
X_EXTRAS = "X-ZENTRALE-EXTRAS"
X_AUS = "X-ZENTRALE-AUS"
X_PAUSE = "X-ZENTRALE-PAUSE"
X_ABSAGE = "X-ZENTRALE-ABSAGE-NOETIG"
X_OHNE_ANFANG = "X-ZENTRALE-OHNE-ANFANG"
X_RRULE_ROH = "X-ZENTRALE-RRULE-ROH"
X_ZEIT_ROH = "X-ZENTRALE-ZEIT-ROH"

# Was ZENTRALE an einem Ereignis selbst verwaltet. Alles ANDERE an einer
# vorhandenen Datei (DESCRIPTION, VALARM, Google-Eigenheiten, ...) wird beim
# Zurückschreiben übernommen — sonst löschte ein Umbenennen in ZENTRALE die
# Notiz, die Sasha am Handy dazugeschrieben hat.
VERWALTET = {"UID", "DTSTAMP", "LAST-MODIFIED", "SUMMARY", "LOCATION",
             "DTSTART", "DTEND", "DURATION", "RRULE", "EXDATE",
             "RECURRENCE-ID"}
VERWALTET_ABWEICHUNG = VERWALTET | {"STATUS"}

# Eine kompakte, regelbasierte Zeitzone. icalendar würde sonst eine Fassung
# mit hunderten RDATEs erzeugen, die nur bis 2038 gilt.
_VTIMEZONE_BERLIN = """BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE
"""


class NichtAbbildbar(ValueError):
    """Dieses Stück lässt sich nicht verlustfrei als VEVENT schreiben. Der
    Speicher legt es dann roh in die Nebendaten."""


def neue_uid() -> str:
    return f"{uuid.uuid4().hex}@zentrale"


# ── kleine Helfer ───────────────────────────────────────────────────────

def _datum(s) -> date | None:
    """ISO-Datum, aber nur wenn es exakt so geschrieben war (sonst wäre die
    Rückübersetzung nicht derselbe Text)."""
    if not isinstance(s, str):
        return None
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return d if d.isoformat() == s else None


def _hhmm(s) -> time | None:
    """'17:45' -> time. Nur die exakte Form HH:MM — '9:30' oder '10' lassen
    sich nicht byte-gleich zurückschreiben und gehen in die Extras."""
    if not isinstance(s, str) or not re.fullmatch(r"\d\d:\d\d", s):
        return None
    h, m = int(s[:2]), int(s[3:])
    if h > 23 or m > 59:
        return None
    return time(h, m)


def _zeit_locker(s) -> time | None:
    """Wie _hhmm, versteht aber auch "10", "9:30", "8" — so stehen Uhrzeiten
    in Sashas echten Daten. Was das genau hieß, bewahrt X-ZENTRALE-ZEIT-ROH."""
    if not isinstance(s, str):
        return None
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", s.strip()) if s == s.strip() else None
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return None
    return time(h, mi)


def _fmt(t) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _ts(d: date, t: time) -> datetime:
    return datetime.combine(d, t).replace(tzinfo=TZ)


def _lokal(dt):
    """Ein Wert aus DTSTART/DTEND in Berliner Ortszeit ohne tzinfo — oder ein
    date bei Ganztags-Werten. Floating Time (ohne TZID) bleibt, wie sie ist;
    UTC und andere Zonen werden umgerechnet."""
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(TZ).replace(tzinfo=None)
        return dt
    return dt


def _xkodieren(obj) -> str:
    """JSON in einer X-Property, base64-verpackt. Grund: Kommas, Semikolons
    und Backslashes behandelt nicht jeder Server gleich (manche escapen sie
    in unbekannten Properties nach). base64 enthält keins davon."""
    roh = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "b64:" + base64.urlsafe_b64encode(roh).decode("ascii")


def _xdekodieren(wert):
    """Gegenstück zu _xkodieren. Tolerant: liest auch rohes JSON. None, wenn
    nichts Brauchbares drinsteht."""
    if wert is None:
        return None
    s = str(wert)
    try:
        if s.startswith("b64:"):
            return json.loads(base64.urlsafe_b64decode(s[4:].encode("ascii")))
        return json.loads(s)
    except Exception:
        return None


def _liste(wert) -> list:
    """Properties, die mehrfach vorkommen dürfen, liefert icalendar mal als
    Einzelwert, mal als Liste."""
    if wert is None:
        return []
    return list(wert) if isinstance(wert, list) else [wert]


def _kalender(komponenten: list, mit_tz: bool) -> Calendar:
    kal = Calendar()
    kal.add("PRODID", PRODID)
    kal.add("VERSION", "2.0")
    if mit_tz:
        kal.add_component(Timezone.from_ical(_VTIMEZONE_BERLIN))
    for k in komponenten:
        kal.add_component(k)
    return kal


def _basis(uid: str, art: str | None, pos, jetzt: datetime) -> Event:
    ev = Event()
    ev.add("UID", uid)
    ev.add("DTSTAMP", jetzt)
    # LAST-MODIFIED ist der Vergleichswert für Grabsteine (kalender_ics):
    # eine Datei, die nicht neuer ist als ihre Löschung, ist ein Geist.
    ev.add("LAST-MODIFIED", jetzt)
    if art:
        ev.add(X_ART, art)
    if pos is not None:
        ev.add(X_POS, str(int(pos)))
    return ev


def _kopf(ev: Event, e: dict, rest: dict) -> None:
    """label, ort, absage_noetig — die Felder, die Termine und Routinen
    teilen. Leere Texte gehen in die Extras: ob ein Server ein leeres
    SUMMARY behält oder wegwirft, ist nicht verlässlich."""
    if isinstance(e.get("label"), str) and e["label"]:
        ev.add("SUMMARY", e["label"])
        rest.pop("label", None)
    if isinstance(e.get("ort"), str) and e["ort"]:
        ev.add("LOCATION", e["ort"])
        rest.pop("ort", None)
    if e.get("absage_noetig") is True:
        ev.add(X_ABSAGE, "TRUE")
        rest.pop("absage_noetig", None)


def _extras_anhaengen(ev: Event, rest: dict) -> None:
    if rest:
        ev.add(X_EXTRAS, _xkodieren(rest))


def _jetzt(jetzt):
    return (jetzt or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)


# ── Schreiben: Termin / Spanne ──────────────────────────────────────────

def termin_kalender(tag: str, e: dict, uid: str, pos=None,
                    jetzt: datetime | None = None) -> Calendar:
    """Ein Einmal-Eintrag (auch eine Spanne mit `bis`) als VCALENDAR.

    `tag` ist der Schlüssel im entries-Dict (bei Spannen der Start-Tag),
    `e` der Eintrag OHNE interne Felder. Wirft NichtAbbildbar, wenn sich das
    Ergebnis nicht exakt zurücklesen lässt."""
    d = _datum(tag)
    if d is None or not isinstance(e, dict):
        raise NichtAbbildbar(f"Termin-Tag {tag!r} oder Eintrag unbrauchbar")
    jetzt = _jetzt(jetzt)
    rest = dict(e)
    roh = {}
    if "bis" in e:
        komps, mit_tz = _spanne(d, e, rest, roh, uid, pos, jetzt)
    else:
        komps, mit_tz = _einzel(d, e, rest, roh, uid, pos, jetzt)
    _roh_anhaengen(komps[0], roh)
    _extras_anhaengen(komps[0], rest)
    kal = _kalender(komps, mit_tz)
    _gegenprobe_termin(kal, tag, e)
    return kal


def _roh_anhaengen(ev: Event, roh: dict) -> None:
    """Uhrzeiten, die nicht in der Form HH:MM standen ("10", "9:30"), gehen
    als 10:00 / 09:30 in DTSTART — Google und das Handy zeigen dann die
    richtige Stunde statt eines Ganztags-Termins. Der Originaltext bleibt
    hier stehen und gilt beim Lesen wieder, SOLANGE die Uhrzeit unverändert
    ist. Verschiebt Sasha den Termin am Handy, gilt die neue Zeit."""
    if roh:
        ev.add(X_ZEIT_ROH, _xkodieren(roh))


def _ende_abbilden(ev, d, t, e, rest, roh, feld="ende"):
    """DTEND aus `ende`, wenn es nach dem Beginn liegt. "24:00" = Mitternacht
    (DTEND am nächsten Tag 00:00, zurückgelesen wieder "24:00" — dieselbe
    Zahl, mit der _interval in kalender.py rechnet)."""
    en = e.get(feld)
    if en == "24:00":
        ev.add("DTEND", _ts(d + timedelta(days=1), time(0)))
        rest.pop(feld, None)
        return
    te = _zeit_locker(en)
    if te and te > t:
        ev.add("DTEND", _ts(d, te))
        rest.pop(feld, None)
        if en != _fmt(te):
            roh[feld] = [en, _fmt(te)]


def _einzel(d, e, rest, roh, uid, pos, jetzt):
    ev = _basis(uid, ART_TERMIN, pos, jetzt)
    _kopf(ev, e, rest)
    t = _zeit_locker(e.get("time"))
    if t:
        ev.add("DTSTART", _ts(d, t))
        rest.pop("time", None)
        if e["time"] != _fmt(t):
            roh["time"] = [e["time"], _fmt(t)]
        _ende_abbilden(ev, d, t, e, rest, roh)
        return [ev], True
    ev.add("DTSTART", d)
    ev.add("DTEND", d + timedelta(days=1))
    return [ev], False


def _tagesfelder(d: date, bis: date, werte: dict, rest_werte: dict) -> dict:
    """Aus `times`/`enden` die Tage holen, die sich abbilden lassen: gültiges
    Datum in der Spanne, lesbare Uhrzeit. -> {tag: (time, originaltext)}.
    Der Rest bleibt in `rest_werte` und wandert in die Extras."""
    gut = {}
    for k, v in werte.items():
        kd = _datum(k)
        tv = _zeit_locker(v)
        if kd and d <= kd <= bis and tv:
            gut[kd] = (tv, v)
        else:
            rest_werte[k] = v
    return gut


def _spanne(d, e, rest, roh, uid, pos, jetzt):
    bis = _datum(e.get("bis"))
    if bis is None or bis < d:
        # kalender.py liest so etwas als eintägige Spanne — das lässt sich
        # nicht sauber ausdrücken, also roh in die Nebendaten.
        raise NichtAbbildbar(f"Spanne mit unbrauchbarem bis={e.get('bis')!r}")
    for feld in ("times", "enden"):
        if feld in e and not isinstance(e[feld], dict):
            raise NichtAbbildbar(f"Spanne mit {feld} vom Typ {type(e[feld]).__name__}")
    rest.pop("bis", None)
    rest_times, rest_enden = {}, {}
    hz = _tagesfelder(d, bis, e.get("times") or {}, rest_times)
    he = _tagesfelder(d, bis, e.get("enden") or {}, rest_enden)
    rest.pop("times", None)
    rest.pop("enden", None)

    ev = _basis(uid, ART_SPANNE, pos, jetzt)
    _kopf(ev, e, rest)
    komps, mit_tz = [ev], False

    def merken(feld, tag, paar):
        t, original = paar
        if original != _fmt(t):
            roh[f"{feld}/{tag.isoformat()}"] = [original, _fmt(t)]

    enden_abgebildet = {}
    if not hz:
        # Form A: ein ganztägiger Block. Enden ohne Beginn kann iCalendar
        # nicht ausdrücken -> Extras.
        rest_enden.update({k.isoformat(): orig for k, (_t, orig) in he.items()})
        ev.add("DTSTART", d)
        ev.add("DTEND", bis + timedelta(days=1))
    elif d != bis and set(hz) == {d} and set(he) <= {bis}:
        # Form B: ein Termin über mehrere Tage mit Beginn am ersten und
        # (optional) Ende am letzten Tag — "Fr 18:00 bis So 14:00".
        mit_tz = True
        ev.add("DTSTART", _ts(d, hz[d][0]))
        merken("times", d, hz[d])
        enden_abgebildet = he
        if bis in he:
            ev.add("DTEND", _ts(bis, he[bis][0]))
            merken("enden", bis, he[bis])
        else:
            ev.add("DTEND", _ts(bis + timedelta(days=1), time(0)))
    else:
        # Form C: tägliche Serie + Abweichungen, alle in DIESER Datei.
        # Ein Ende braucht hier einen Beginn am selben Tag, der davor liegt.
        mit_tz = True
        he_ok = {}
        for k, (v, orig) in he.items():
            if k in hz and v > hz[k][0]:
                he_ok[k] = (v, orig)
            else:
                rest_enden[k.isoformat()] = orig
        enden_abgebildet = he_ok
        tage = (bis - d).days + 1
        ev.add("DTSTART", d)
        ev.add("DTEND", d + timedelta(days=1))
        ev.add("RRULE", {"FREQ": "DAILY", "COUNT": tage})
        for tag in sorted(hz):
            ab = _basis(uid, None, None, jetzt)
            ab.add("RECURRENCE-ID", tag)
            ab.add("DTSTART", _ts(tag, hz[tag][0]))
            merken("times", tag, hz[tag])
            if tag in he_ok:
                ab.add("DTEND", _ts(tag, he_ok[tag][0]))
                merken("enden", tag, he_ok[tag])
            # Titel und Ort mitgeben: Google zeigt eine Abweichung als
            # eigenes Ereignis, ohne SUMMARY stünde dort ein leerer Termin.
            if ev.get("SUMMARY") is not None:
                ab.add("SUMMARY", str(ev.get("SUMMARY")))
            if ev.get("LOCATION") is not None:
                ab.add("LOCATION", str(ev.get("LOCATION")))
            komps.append(ab)

    # Was nicht abgebildet wurde, in die Extras. Ein vorhandenes, aber
    # leeres `times` bleibt so ebenfalls erhalten.
    if rest_times or ("times" in e and not hz):
        rest["times"] = rest_times
    if rest_enden or ("enden" in e and not enden_abgebildet):
        rest["enden"] = rest_enden
    return komps, mit_tz


def _gegenprobe_termin(kal, tag, e):
    gelesen = lesen(kal)
    if (len(gelesen) != 1 or gelesen[0]["art"] != "termin"
            or gelesen[0]["tag"] != tag or gelesen[0]["daten"] != e):
        raise NichtAbbildbar(f"Termin {e.get('label')!r} am {tag} liest sich "
                             f"nicht exakt zurück")


# ── Schreiben: Routine ──────────────────────────────────────────────────

def anker_ausrichten(r: dict, anker: date) -> date:
    """Der erste echte Termin der Regel ab `anker`. Nach RFC 5545 ist DTSTART
    immer das erste Vorkommen — läge er auf einem Tag, den die Regel gar
    nicht trifft, zeigte Google dort einen Termin zu viel."""
    try:
        occ = kalender_regel.vorkommen({**r, "seit": anker.isoformat()},
                                       anker, anker + timedelta(days=800))
        if occ:
            return occ[0].date()
    except Exception:
        pass
    return anker


def _regel_text(rr) -> str:
    """Eine RRULE als Text, UNTIL in Ortszeit ohne Zone. So rechnet dateutil
    sie mit dem zonenlosen Start in kalender_regel (gemischte Zonen wirft es
    sonst ab)."""
    rr = vRecur(dict(rr))
    if "UNTIL" in rr:
        u = rr["UNTIL"][0] if isinstance(rr["UNTIL"], list) else rr["UNTIL"]
        if isinstance(u, datetime) and u.tzinfo is not None:
            rr["UNTIL"] = [u.astimezone(TZ).replace(tzinfo=None)]
    return rr.to_ical().decode("ascii")


def routine_kalender(r: dict, uid: str, pos=None, pausen: list | None = None,
                     anker: date | None = None,
                     jetzt: datetime | None = None) -> Calendar:
    """Eine Routine als VCALENDAR.

    pausen – [(nr, pause_dict)] aus der top-level `pausen`-Liste, deren
             label zu dieser Routine passt (gleiche Regel wie _pause_grund).
             `nr` ist die Stelle in der Liste, damit die Reihenfolge beim
             Zurücklesen wieder stimmt.
    anker  – technischer Start für Routinen OHNE `seit` (die alte JSON kannte
             keinen Anfang). Wird auf das erste Vorkommen ausgerichtet.
    """
    if not isinstance(r, dict):
        raise NichtAbbildbar("Routine ist kein Dict")
    regel = r.get("rrule")
    if not isinstance(regel, str) or not kalender_regel.regel_gueltig(regel):
        raise NichtAbbildbar(f"Routine mit unbrauchbarer rrule {regel!r}")
    try:
        vr = vRecur.from_ical(regel)
    except Exception as ex:
        raise NichtAbbildbar(f"rrule {regel!r} nicht als iCalendar lesbar: {ex}")
    jetzt = _jetzt(jetzt)
    pausen = list(pausen or [])
    rest = dict(r)
    rest.pop("rrule", None)

    ev = _basis(uid, ART_ROUTINE, pos, jetzt)
    _kopf(ev, r, rest)

    seit = _datum(r.get("seit"))
    if seit is not None:
        start_d = seit
        rest.pop("seit", None)
    else:
        start_d = anker_ausrichten(r, anker or date.today())
        ev.add(X_OHNE_ANFANG, "TRUE")

    roh = {}
    t = _zeit_locker(r.get("time"))
    if t:
        rest.pop("time", None)
        if r["time"] != _fmt(t):
            roh["time"] = [r["time"], _fmt(t)]
        ev.add("DTSTART", _ts(start_d, t))
        _ende_abbilden(ev, start_d, t, r, rest, roh)
    else:
        ev.add("DTSTART", start_d)
        ev.add("DTEND", start_d + timedelta(days=1))
    _roh_anhaengen(ev, roh)

    # UNTIL muss zum Typ von DTSTART passen (RFC 5545): mit Zone -> UTC,
    # ganztags -> Datum.
    if "UNTIL" in vr:
        u = vr["UNTIL"][0] if isinstance(vr["UNTIL"], list) else vr["UNTIL"]
        if t:
            if not isinstance(u, datetime):
                u = datetime.combine(u, time(23, 59, 59))
            if u.tzinfo is None:
                u = u.replace(tzinfo=TZ)
            vr["UNTIL"] = [u.astimezone(timezone.utc)]
        elif isinstance(u, datetime):
            vr["UNTIL"] = [_lokal(u).date()]
    ev.add("RRULE", vr)
    geschrieben = _regel_text(ev["RRULE"])
    if geschrieben != regel:
        # icalendar ordnet die Teile einer Regel um ("BYMONTH=12;BYMONTHDAY=25"
        # -> umgekehrt). Gleichbedeutend, aber nicht derselbe Text — also das
        # Original aufheben. Es gilt nur, solange die RRULE unverändert ist.
        ev.add(X_RRULE_ROH, _xkodieren({"roh": regel, "geschrieben": geschrieben}))

    # aus + Pausen -> EXDATE. X-ZENTRALE-AUS behält die genaue Liste (auch
    # Reihenfolge und Daten, die gar kein Vorkommen sind).
    weg = set()
    aus = r.get("aus")
    if "aus" in r and isinstance(aus, list) and all(isinstance(a, str) for a in aus):
        ev.add(X_AUS, _xkodieren(aus))
        rest.pop("aus", None)
        weg |= {d for d in (_datum(a) for a in aus) if d}
    for nr, p in pausen:
        ev.add(X_PAUSE, _xkodieren(p), parameters={"X-NR": str(int(nr))})
        weg |= set(_pausen_tage(r, p))
    if weg:
        ev.add("EXDATE", [(_ts(d, t) if t else d) for d in sorted(weg)])

    komps = [ev]
    abw = r.get("abweichungen")
    if "abweichungen" in r:
        if not isinstance(abw, dict):
            raise NichtAbbildbar("abweichungen ist kein Dict")
        rest_abw = {}
        for rid, a in abw.items():
            k = _abweichung_komponente(uid, rid, a, t, ev, jetzt)
            if k is None:
                rest_abw[rid] = a
            else:
                komps.append(k)
        rest.pop("abweichungen", None)
        if rest_abw or not abw:
            rest["abweichungen"] = rest_abw

    _extras_anhaengen(ev, rest)
    kal = _kalender(komps, mit_tz=bool(t) or len(komps) > 1)
    gelesen = lesen(kal)
    if (len(gelesen) != 1 or gelesen[0]["art"] != "routine"
            or gelesen[0]["daten"] != r
            or sorted(gelesen[0]["pausen"], key=_pausen_key) != sorted(pausen, key=_pausen_key)):
        raise NichtAbbildbar(f"Routine {r.get('label')!r} liest sich nicht "
                             f"exakt zurück")
    return kal


def _pausen_key(np):
    return (np[0], json.dumps(np[1], sort_keys=True, ensure_ascii=False))


def _pausen_tage(r: dict, p: dict) -> list:
    """Die Vorkommen der Routine innerhalb einer Pause (für EXDATE)."""
    if not isinstance(p, dict):
        return []
    von, bis = _datum(p.get("von")), _datum(p.get("bis"))
    if not von or not bis or bis < von:
        return []
    try:
        return [o.date() for o in kalender_regel.vorkommen(r, von, bis)]
    except Exception:
        return []


_ABW_FELDER = {"tag", "time", "ende", "label", "ort", "entfaellt"}


def _abweichung_komponente(uid, rid, a, t, master, jetzt):
    """Eine Abweichung einer Routine (am Handy verschobener Einzeltermin) als
    Komponente mit RECURRENCE-ID. None, wenn sie sich nicht exakt ausdrücken
    lässt — dann bleibt sie in den Extras."""
    rid_d = _datum(rid)
    if rid_d is None or not isinstance(a, dict) or not set(a) <= _ABW_FELDER:
        return None
    ab = _basis(uid, None, None, jetzt)
    ab.add("RECURRENCE-ID", _ts(rid_d, t) if t else rid_d)
    if a.get("entfaellt") is True and set(a) == {"entfaellt"}:
        ab.add("STATUS", "CANCELLED")
        ab.add("DTSTART", _ts(rid_d, t) if t else rid_d)
        return ab
    tag = _datum(a.get("tag"))
    if tag is None or "entfaellt" in a:
        return None
    at = _hhmm(a.get("time")) if "time" in a else None
    if "time" in a and at is None:
        return None
    ae = _hhmm(a.get("ende")) if "ende" in a else None
    if "ende" in a and (ae is None or at is None or ae <= at):
        return None
    m_label = str(master.get("SUMMARY") or "")
    m_ort = str(master.get("LOCATION") or "")
    # Ein eigener Titel/Ort zählt nur, wenn er sich vom Master unterscheidet
    # — genau so liest _routine_lesen ihn zurück.
    for feld, m_wert in (("label", m_label), ("ort", m_ort)):
        if feld in a and (not isinstance(a[feld], str) or not a[feld]
                          or a[feld] == m_wert):
            return None
    if at:
        ab.add("DTSTART", _ts(tag, at))
        if ae:
            ab.add("DTEND", _ts(tag, ae))
    else:
        ab.add("DTSTART", tag)
    label = a.get("label") or m_label
    ort = a.get("ort") or m_ort
    if label:
        ab.add("SUMMARY", label)
    if ort:
        ab.add("LOCATION", ort)
    return ab


# ── Lesen ───────────────────────────────────────────────────────────────

def lesen(kal: Calendar) -> list[dict]:
    """Alle Stücke (je UID eins) eines VCALENDAR.

    -> [{uid, art: 'termin'|'routine', tag (nur termin), daten, pos,
         pausen: [(nr, dict)], anker (Datum des DTSTART), geaendert}]
    Stücke ohne brauchbares DTSTART werden übersprungen (der Aufrufer
    sieht sie nicht; die Datei bleibt unangetastet liegen)."""
    nach_uid: dict[str, list] = {}
    for ev in kal.walk("VEVENT"):
        uid = str(ev.get("UID") or "")
        nach_uid.setdefault(uid, []).append(ev)
    raus = []
    for uid, evs in nach_uid.items():
        master = next((e for e in evs if e.get("RECURRENCE-ID") is None), None)
        abw = [e for e in evs if e.get("RECURRENCE-ID") is not None]
        if master is None or master.get("DTSTART") is None:
            continue
        try:
            stueck = _stueck_lesen(uid, master, abw)
        except Exception:
            continue
        if stueck:
            raus.append(stueck)
    return raus


def geaendert_um(ev) -> datetime | None:
    """LAST-MODIFIED (sonst DTSTAMP) als UTC-Zeit — der Vergleichswert für
    Grabsteine."""
    for name in ("LAST-MODIFIED", "DTSTAMP"):
        v = ev.get(name)
        if v is None:
            continue
        dt = v.dt
        if isinstance(dt, datetime):
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    return None


def _stueck_lesen(uid, master, abw):
    art = str(master.get(X_ART) or "").upper()
    pos = None
    try:
        if master.get(X_POS) is not None:
            pos = int(str(master.get(X_POS)))
    except ValueError:
        pos = None
    extras = _xdekodieren(master.get(X_EXTRAS))
    extras = extras if isinstance(extras, dict) else {}

    start = _lokal(master.get("DTSTART").dt)
    ende = _ende_lesen(master, start)
    rr = master.get("RRULE")

    if art not in (ART_TERMIN, ART_SPANNE, ART_ROUTINE):
        art = _art_raten(start, ende, rr)

    basis = {"uid": uid, "pos": pos, "pausen": [],
             "geaendert": geaendert_um(master),
             "anker": start.date() if isinstance(start, datetime) else start}
    if art == ART_ROUTINE:
        daten, pausen = _routine_lesen(master, abw, start, ende, rr, extras)
        return {**basis, "art": "routine", "daten": daten, "pausen": pausen}
    tag = start.date() if isinstance(start, datetime) else start
    if art == ART_SPANNE:
        daten = _spanne_lesen(master, abw, start, ende, rr, extras)
    else:
        daten = _termin_lesen(master, start, ende, extras)
    return {**basis, "art": "termin", "tag": tag.isoformat(), "daten": daten}


def _ende_lesen(ev, start):
    v = ev.get("DTEND")
    if v is not None:
        return _lokal(v.dt)
    d = ev.get("DURATION")
    if d is not None:
        return start + d.dt
    return None


def _art_raten(start, ende, rr) -> str:
    """Ein Ereignis ohne X-ZENTRALE-ART kommt von außen (Google, Handy,
    khal). Eine endliche, schlichte Tagesserie ist eine Spanne mit eigener
    Zeit pro Tag (so hat Sasha die Spanne entschieden); jede andere Regel
    eine Routine; ein Termin über mehrere Tage eine Spanne."""
    if rr is not None:
        teile = {k.upper() for k in rr}
        einfach = teile <= {"FREQ", "COUNT", "UNTIL", "INTERVAL", "WKST"}
        intervall = rr.get("INTERVAL", [1])
        intervall = intervall[0] if isinstance(intervall, list) else intervall
        freq = rr.get("FREQ", [""])
        freq = freq[0] if isinstance(freq, list) else freq
        endlich = "COUNT" in rr or "UNTIL" in rr
        if str(freq).upper() == "DAILY" and einfach and endlich and int(intervall) == 1:
            return ART_SPANNE
        return ART_ROUTINE
    if isinstance(start, datetime):
        if ende is not None and ende.date() > start.date():
            mitternacht = datetime.combine(start.date() + timedelta(days=1), time(0))
            return ART_TERMIN if ende == mitternacht else ART_SPANNE
        return ART_TERMIN
    if ende is not None and isinstance(ende, date) and (ende - start).days > 1:
        return ART_SPANNE
    return ART_TERMIN


def _kopf_lesen(ev, daten: dict) -> None:
    if ev.get("SUMMARY") is not None and str(ev.get("SUMMARY")):
        daten["label"] = str(ev.get("SUMMARY"))
    if ev.get("LOCATION") is not None and str(ev.get("LOCATION")):
        daten["ort"] = str(ev.get("LOCATION"))
    if str(ev.get(X_ABSAGE) or "").upper() == "TRUE":
        daten["absage_noetig"] = True


def _roh_anwenden(ev, daten: dict) -> None:
    """Originaltexte von Uhrzeiten zurücksetzen — aber nur, wo die Uhrzeit
    noch genau die ist, die ZENTRALE daraus gemacht hatte (siehe
    _roh_anhaengen)."""
    roh = _xdekodieren(ev.get(X_ZEIT_ROH))
    if not isinstance(roh, dict):
        return
    for pfad, paar in roh.items():
        if not (isinstance(paar, list) and len(paar) == 2):
            continue
        original, geschrieben = paar
        feld, _, tag = str(pfad).partition("/")
        if not tag:
            if daten.get(feld) == geschrieben:
                daten[feld] = original
        elif isinstance(daten.get(feld), dict) and daten[feld].get(tag) == geschrieben:
            daten[feld][tag] = original


def _luecken_fuellen(daten: dict, extras: dict, tagesfelder=()) -> dict:
    """Extras füllen nur Lücken: was die Properties sagen, gewinnt. So
    überschreibt ein alter Rohwert nie eine Änderung, die am Handy
    gemacht wurde. Bei den Tages-Dicts (times/enden/abweichungen) gilt das
    pro Tag."""
    for k, v in extras.items():
        if k in tagesfelder and isinstance(v, dict) and isinstance(daten.get(k), dict):
            for tk, tv in v.items():
                daten[k].setdefault(tk, tv)
        elif k not in daten:
            daten[k] = v
    return daten


def _termin_lesen(ev, start, ende, extras):
    daten = {}
    _kopf_lesen(ev, daten)
    if isinstance(start, datetime):
        daten["time"] = _fmt(start)
        if isinstance(ende, datetime) and ende > start:
            if ende.date() == start.date():
                daten["ende"] = _fmt(ende)
            elif ende == datetime.combine(start.date() + timedelta(days=1), time(0)):
                daten["ende"] = "24:00"
    _roh_anwenden(ev, daten)
    return _luecken_fuellen(daten, extras)


def _spanne_lesen(ev, abw, start, ende, rr, extras):
    daten = {}
    _kopf_lesen(ev, daten)
    von = start.date() if isinstance(start, datetime) else start
    times, enden = {}, {}
    if rr is not None:
        n = rr.get("COUNT")
        n = n[0] if isinstance(n, list) else n
        if n:
            bis = von + timedelta(days=int(n) - 1)
        else:
            u = rr.get("UNTIL")
            u = u[0] if isinstance(u, list) else u
            u = _lokal(u)
            bis = u.date() if isinstance(u, datetime) else u
        # Grundzeit aus dem Master, dann die Abweichungen pro Tag.
        basis_t = start.time() if isinstance(start, datetime) else None
        basis_e = (ende.time() if isinstance(ende, datetime) and isinstance(start, datetime)
                   and ende.date() == start.date() and ende > start else None)
        pro_tag = {}
        for a in abw:
            rid = _lokal(a.get("RECURRENCE-ID").dt)
            rid_d = rid.date() if isinstance(rid, datetime) else rid
            a_s = _lokal(a.get("DTSTART").dt) if a.get("DTSTART") is not None else None
            a_e = _ende_lesen(a, a_s) if a_s is not None else None
            pro_tag[rid_d] = (a_s, a_e)
        cur = von
        while cur <= bis:
            t, e = basis_t, basis_e
            if cur in pro_tag:
                a_s, a_e = pro_tag[cur]
                t = a_s.time() if isinstance(a_s, datetime) else None
                e = (a_e.time() if isinstance(a_e, datetime) and isinstance(a_s, datetime)
                     and a_e.date() == a_s.date() and a_e > a_s else None)
            if t is not None:
                times[cur.isoformat()] = _fmt(t)
                if e is not None:
                    enden[cur.isoformat()] = _fmt(e)
            cur += timedelta(days=1)
    elif isinstance(start, datetime):
        times[von.isoformat()] = _fmt(start)
        if isinstance(ende, datetime) and ende > start:
            if ende.time() == time(0):
                bis = ende.date() - timedelta(days=1)
            else:
                bis = ende.date()
                enden[bis.isoformat()] = _fmt(ende)
        else:
            bis = von
    else:
        bis = (ende - timedelta(days=1)) if isinstance(ende, date) and ende > von else von
    daten["bis"] = bis.isoformat()
    if times:
        daten["times"] = times
    if enden:
        daten["enden"] = enden
    _roh_anwenden(ev, daten)
    return _luecken_fuellen(daten, extras, tagesfelder=("times", "enden"))


def _routine_lesen(ev, abw, start, ende, rr, extras):
    daten = {}
    _kopf_lesen(ev, daten)
    regel = _regel_text(rr)
    roh = _xdekodieren(ev.get(X_RRULE_ROH))
    if isinstance(roh, dict) and roh.get("geschrieben") == regel and isinstance(roh.get("roh"), str):
        regel = roh["roh"]
    daten["rrule"] = regel
    if isinstance(start, datetime):
        daten["time"] = _fmt(start)
        if isinstance(ende, datetime) and ende > start:
            if ende.date() == start.date():
                daten["ende"] = _fmt(ende)
            elif ende == datetime.combine(start.date() + timedelta(days=1), time(0)):
                daten["ende"] = "24:00"
    _roh_anwenden(ev, daten)
    if str(ev.get(X_OHNE_ANFANG) or "").upper() != "TRUE":
        daten["seit"] = (start.date() if isinstance(start, datetime) else start).isoformat()

    pausen = []
    for p in _liste(ev.get(X_PAUSE)):
        obj = _xdekodieren(p)
        try:
            nr = int(p.params.get("X-NR"))
        except (TypeError, ValueError, AttributeError):
            nr = 10**6 + len(pausen)          # ohne Nummer: hinten anstellen
        if obj is not None:
            pausen.append((nr, obj))

    # EXDATE: was nicht durch X-ZENTRALE-AUS oder eine Pause erklärt ist,
    # wurde außerhalb gelöscht (am Handy "nur diesen Termin löschen") und
    # gilt in ZENTRALE als einzeln deaktiviert.
    x_aus = _xdekodieren(ev.get(X_AUS))
    x_aus = x_aus if isinstance(x_aus, list) else None
    ex_tage = set()
    for liste in _liste(ev.get("EXDATE")):
        for v in getattr(liste, "dts", []):
            w = _lokal(v.dt)
            ex_tage.add(w.date() if isinstance(w, datetime) else w)
    erklaert = {d for d in (_datum(a) for a in (x_aus or [])) if d}
    for _nr, p in pausen:
        erklaert |= set(_pausen_tage(daten, p))
    extern = sorted(ex_tage - erklaert)
    if x_aus is not None or extern:
        daten["aus"] = list(x_aus or []) + [d.isoformat() for d in extern]

    if abw:
        ab_dict = {}
        for a in abw:
            rid = _lokal(a.get("RECURRENCE-ID").dt)
            rid_d = rid.date() if isinstance(rid, datetime) else rid
            if str(a.get("STATUS") or "").upper() == "CANCELLED":
                ab_dict[rid_d.isoformat()] = {"entfaellt": True}
                continue
            a_s = _lokal(a.get("DTSTART").dt) if a.get("DTSTART") is not None else None
            if a_s is None:
                continue
            a_e = _ende_lesen(a, a_s)
            eintrag = {"tag": (a_s.date() if isinstance(a_s, datetime) else a_s).isoformat()}
            if isinstance(a_s, datetime):
                eintrag["time"] = _fmt(a_s)
                if isinstance(a_e, datetime) and a_e.date() == a_s.date() and a_e > a_s:
                    eintrag["ende"] = _fmt(a_e)
            s = str(a.get("SUMMARY") or "")
            if s and s != daten.get("label", ""):
                eintrag["label"] = s
            o = str(a.get("LOCATION") or "")
            if o and o != daten.get("ort", ""):
                eintrag["ort"] = o
            ab_dict[rid_d.isoformat()] = eintrag
        daten["abweichungen"] = ab_dict
    daten = _luecken_fuellen(daten, extras, tagesfelder=("abweichungen",))
    return daten, sorted(pausen, key=_pausen_key)


# ── Zusammenführen: alte Datei + neue Fassung ───────────────────────────

def zusammenfuehren(alt: bytes | None, neu: Calendar, uid: str) -> bytes:
    """Die neue Fassung eines Stücks in eine vorhandene Datei einsetzen,
    ohne fremde Inhalte zu verlieren:
      * Properties, die ZENTRALE nicht verwaltet (DESCRIPTION, Erinnerungen,
        Google-Felder), werden von der alten Komponente gleicher
        RECURRENCE-ID übernommen; ebenso VALARM-Unterkomponenten.
      * Komponenten mit ANDERER UID in derselben Datei bleiben unberührt.
      * Kalender-weite Properties (X-WR-CALNAME …) bleiben.
    Lässt sich die alte Datei nicht lesen, gilt nur die neue (die alte liegt
    da schon im Verlauf)."""
    if not alt:
        return neu.to_ical()
    try:
        alt_kal = Calendar.from_ical(alt)
    except Exception:
        return neu.to_ical()

    def schluessel(ev):
        r = ev.get("RECURRENCE-ID")
        return None if r is None else r.to_ical()

    alte = {schluessel(ev): ev for ev in alt_kal.walk("VEVENT")
            if str(ev.get("UID") or "") == uid}

    raus = Calendar()
    for name, wert in neu.property_items(recursive=False):
        if name not in ("BEGIN", "END"):
            raus.add(name, wert)
    for name, wert in alt_kal.property_items(recursive=False):
        if name not in ("BEGIN", "END") and raus.get(name) is None:
            raus.add(name, wert)

    zonen = {}
    for tz in list(neu.walk("VTIMEZONE")) + list(alt_kal.walk("VTIMEZONE")):
        zonen.setdefault(str(tz.get("TZID")), tz)
    for tz in zonen.values():
        raus.add_component(tz)

    for ev in neu.walk("VEVENT"):
        alt_ev = alte.get(schluessel(ev))
        if alt_ev is not None:
            verwaltet = VERWALTET_ABWEICHUNG if ev.get("RECURRENCE-ID") is not None else VERWALTET
            # Namen, die die neue Fassung schon hat, bleiben ihre; von den
            # übrigen werden ALLE Vorkommen übernommen (ATTENDEE, mehrere
            # CATEGORIES …).
            schon_da = {name for name, _w in ev.property_items(recursive=False)}
            for name, wert in alt_ev.property_items(recursive=False):
                if name in ("BEGIN", "END") or name in verwaltet or name in schon_da:
                    continue
                if name.startswith("X-ZENTRALE-"):
                    continue
                ev.add(name, wert)
            if not ev.subcomponents:
                for sub in alt_ev.subcomponents:
                    ev.add_component(sub)
        raus.add_component(ev)

    for komp in alt_kal.subcomponents:
        if komp.name == "VTIMEZONE":
            continue
        if komp.name == "VEVENT" and str(komp.get("UID") or "") == uid:
            continue
        raus.add_component(komp)
    return raus.to_ical()


def datei_lesen(roh: bytes) -> list[dict]:
    """Bytes einer .ics-Datei -> Stücke. Wirft bei kaputtem iCalendar
    (der Speicher fängt das und lässt die Datei liegen)."""
    return lesen(Calendar.from_ical(roh))
