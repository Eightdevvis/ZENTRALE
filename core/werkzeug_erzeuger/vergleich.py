# core/werkzeug_erzeuger/vergleich.py
#
# „Steht es so da, wie verlangt?“ für Anbindungen (2026-10-11). Ein fremdes
# Programm gibt zurück, was es gespeichert hat — in SEINER Schreibweise:
# der eigene Kalender zeigt „9:00“, wo wir „09:00“ schickten; ein anderer
# liefert „2026-11-03T09:00:00+01:00“. Gleiches muss gleich gelten, sonst
# nimmt der Erzeuger jedes Mal zurück, was richtig war. Deshalb sagt die
# Beschreibung je Feld, WIE verglichen wird (Normalisierung) — eine feste,
# kleine Liste, keine Formeln:
#
#   text             Leerraum zusammengezogen, Unicode normalisiert
#   zahl             3, 3.0 und "3" sind gleich
#   datum            2026-11-03, 20261103, 2026-11-03T09:00 (nur der Tag)
#   uhrzeit          9:00, 09:00, 09:00:00, 2026-11-03T09:00 → 09:00
#   zeitpunkt        Tag + Uhrzeit MIT Zeitzone (ohne Angabe: die der
#                    Anbindung, Kopf `zeitzone`); verglichen wird derselbe
#                    Moment, nicht die Schreibweise
#   liste-ungeordnet gleiche Elemente, Reihenfolge egal
#   wahrheit         true/false, ja/nein, 1/0

import re
import unicodedata
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .vorlage import zeiger_eins

NORMEN = ("text", "zahl", "datum", "uhrzeit", "zeitpunkt", "liste-ungeordnet", "wahrheit")


class NichtVergleichbar(ValueError):
    """Der Wert lässt sich nicht in die Normalform bringen."""


def _text(w) -> str:
    if isinstance(w, bool):
        return "true" if w else "false"
    return " ".join(unicodedata.normalize("NFC", str(w)).split())


def _zahl(w):
    if isinstance(w, bool):
        raise NichtVergleichbar(f"{w!r} ist keine Zahl")
    try:
        return Decimal(str(w).strip().replace(",", ".")).normalize()
    except InvalidOperation:
        raise NichtVergleichbar(f"{w!r} ist keine Zahl")


def _datum(w):
    s = str(w).strip()
    try:
        if re.fullmatch(r"\d{8}", s):
            return date(int(s[:4]), int(s[4:6]), int(s[6:]))
        return date.fromisoformat(s[:10])
    except ValueError:
        raise NichtVergleichbar(f"{w!r} ist kein Datum")


def _uhrzeit(w):
    s = str(w).strip()
    if "T" in s:
        s = s.split("T", 1)[1]
    s = re.split(r"[+Z-]", s, maxsplit=1)[0]
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?", s)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise NichtVergleichbar(f"{w!r} ist keine Uhrzeit")
    return time(int(m.group(1)), int(m.group(2)))


def _zeitpunkt(w, zone):
    s = str(w).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise NichtVergleichbar(f"{w!r} ist kein Zeitpunkt (YYYY-MM-DDTHH:MM[:SS][+hh:mm])")
    if d.tzinfo is None:
        if not zone:
            raise NichtVergleichbar(f"{w!r} hat keine Zeitzone und die Anbindung nennt keine")
        try:
            d = d.replace(tzinfo=ZoneInfo(zone))
        except ZoneInfoNotFoundError:
            raise NichtVergleichbar(f"Zeitzone {zone!r} gibt es nicht")
    return d.astimezone(timezone.utc)


def _wahrheit(w):
    if isinstance(w, bool):
        return w
    s = str(w).strip().lower()
    if s in ("true", "ja", "1", "yes", "wahr"):
        return True
    if s in ("false", "nein", "0", "no", "falsch"):
        return False
    raise NichtVergleichbar(f"{w!r} ist weder wahr noch falsch")


def normal(norm: str, wert, zone=None):
    """Die Normalform eines Werts (vergleichbar mit ==)."""
    if norm == "text":
        return _text(wert)
    if norm == "zahl":
        return _zahl(wert)
    if norm == "datum":
        return _datum(wert)
    if norm == "uhrzeit":
        return _uhrzeit(wert)
    if norm == "zeitpunkt":
        return _zeitpunkt(wert, zone)
    if norm == "wahrheit":
        return _wahrheit(wert)
    if norm == "liste-ungeordnet":
        if not isinstance(wert, (list, tuple)):
            raise NichtVergleichbar(f"{wert!r} ist keine Liste")
        return sorted(_text(x) for x in wert)
    raise NichtVergleichbar(f"Normalisierung {norm!r} gibt es nicht")


def gleich(norm: str, verlangt, da, zone=None) -> bool:
    return normal(norm, verlangt, zone) == normal(norm, da, zone)


def abweichungen(regeln: dict, args: dict, eintrag: dict, zone=None) -> list:
    """Die Felder, die nachgelesen anders dastehen als verlangt. `regeln`:
    Argument → {norm, feld?, muster?}. Verglichen wird nur, was angegeben
    wurde. `feld` ist ein Zeiger in den Eintrag (Standard: '/<Argument>');
    `muster` ein Ausdruck mit einer Gruppe, der aus dem Feld den Teil holt,
    der gemeint ist (Kalender: UNTIL=… aus der Wiederholungsregel)."""
    falsch = []
    for name, regel in regeln.items():
        if name not in args:
            continue
        verlangt = args[name]
        da = zeiger_eins(eintrag, regel.get("feld") or "/" + name)
        if da is not None and regel.get("muster"):
            m = re.search(regel["muster"], str(da))
            da = m.group(1) if m else None
        if da is None:
            falsch.append(f"{name} verlangt {verlangt!r}, steht nicht da")
            continue
        try:
            ok = gleich(regel["norm"], verlangt, da, zone)
        except NichtVergleichbar as e:
            falsch.append(f"{name}: {e}")
            continue
        if not ok:
            falsch.append(f"{name} verlangt {verlangt!r}, steht {da!r}")
    return falsch
