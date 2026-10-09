# core/zusagen.py
#
# Offene Zusagen der KI je Gespräch: „trag ich gleich ein" — und dann kam
# nichts. Erkannt werden sie in core/ehrlichkeit_erkennen.py, abgehakt in
# core/ehrlichkeit.py; hier steht nur, wo sie liegen (2026-10-09,
# memory/ki/ehrlichkeit_live.md).
#
#   data/gespraeche/<id>/zusagen-<knoten>.json
#     {"zusagen":  [{id, satz, bereiche, stichwoerter, schreibend, zug, ts, art?}],
#      "erledigt": {id: {grund, zug, ts}},
#      "bezug":    {id: zug}}
#
# Eine Datei PRO RECHNER, wie die Nachrichten (core/gespraeche.py): der
# Abgleich ist „neueste Datei gewinnt", und zwei Rechner, die in dieselbe
# Datei schreiben, verlören einer des anderen Einträge. Eine Zusage vom
# Laptop, die am PC eingelöst wird, bekommt ihr „erledigt" in der Datei des
# PCs; gelesen wird über alle Dateien des Gesprächs. Nie gelöscht, nur
# abgehakt. Der Ordner folgt gespraeche._DIR (in Tests umgelenkt über
# ZENTRALE_GESPRAECHE_DIR).
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import threading
import uuid

import dateien
import gespraeche

_lock = threading.Lock()
_VORSILBE = "zusagen-"


def _pfad(gid, kn=None):
    kn = dateien.sicherer_name(kn or gespraeche.knoten())
    return os.path.join(gespraeche._ordner(gid), f"{_VORSILBE}{kn}.json")


def _lesen(pfad) -> dict:
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _eigene():
    return {"zusagen": [], "erledigt": {}, "bezug": {}}


def _alle_dateien(gid) -> list:
    try:
        namen = os.listdir(gespraeche._ordner(gid))
    except OSError:
        return []
    return [os.path.join(gespraeche._ordner(gid), n) for n in sorted(namen)
            if n.startswith(_VORSILBE) and n.endswith(".json")]


def _zusammen(gid):
    """-> (zusagen, erledigt, bezug) über alle Rechner."""
    liste, erledigt, bezug = [], {}, {}
    for p in _alle_dateien(gid):
        d = _lesen(p)
        for z in d.get("zusagen") or []:
            if isinstance(z, dict) and z.get("id") and z.get("satz"):
                liste.append(z)
        erledigt.update({k: v for k, v in (d.get("erledigt") or {}).items()})
        for k, v in (d.get("bezug") or {}).items():
            if isinstance(v, int):
                bezug[k] = max(v, bezug.get(k, 0))
    liste.sort(key=lambda z: (z.get("zug") or 0, z.get("ts") or ""))
    return liste, erledigt, bezug


def offen(gid) -> list:
    """Die offenen Zusagen, älteste zuerst: [{id, satz, bereiche, zug, …}]."""
    if not gespraeche.gibt_es(gid):
        return []
    liste, erledigt, bezug = _zusammen(gid)
    raus = []
    for z in liste:
        if z["id"] in erledigt:
            continue
        raus.append(dict(z, zuletzt=max(z.get("zug") or 0, bezug.get(z["id"], 0))))
    return raus


def _aendern(gid, was):
    """Die eigene Datei lesen, ändern, atomar schreiben."""
    with _lock:
        pfad = _pfad(gid)
        d = _lesen(pfad) or _eigene()
        for k, v in _eigene().items():
            d.setdefault(k, v)
        was(d)
        dateien.json_schreiben(pfad, d)


def hinzufuegen(gid, neue, zug: int) -> list:
    """Neue Zusagen (ehrlichkeit_erkennen.Zusage) merken. -> ihre ids.
    Derselbe Satz, der schon offen ist, kommt nicht doppelt."""
    if not neue or not gespraeche.gibt_es(gid):
        return []
    schon = {z["satz"] for z in offen(gid)}
    eintraege = []
    for z in neue:
        if z.satz in schon:
            continue
        schon.add(z.satz)
        eintraege.append({"id": uuid.uuid4().hex[:12], "satz": z.satz,
                          "bereiche": sorted(z.bereiche), "stichwoerter": list(z.stichwoerter),
                          "schreibend": bool(getattr(z, "schreibend", True)),
                          "zug": int(zug), "ts": gespraeche.jetzt_ts()})
    if eintraege:
        _aendern(gid, lambda d: d["zusagen"].extend(eintraege))
    return [e["id"] for e in eintraege]


def merken(gid, art: str, satz: str, zug: int) -> str | None:
    """Eine Zusage, die ein WERKZEUG einträgt, nicht die Erkennung im Text
    (2026-10-09: „input_aufraeumen: <datei>", core/input_aufraeumen.py).
    `art` ist ihr Schlüssel: dieselbe Art kommt nicht doppelt, und abgehakt
    wird sie nur von dem, der sie eingetragen hat — nachfuehren lässt sie
    in Ruhe (kein Verfall, kein „irgendein Werkzeug lief"). -> id oder None."""
    if not art or not gespraeche.gibt_es(gid):
        return None
    if any(z.get("art") == art for z in offen(gid)):
        return None
    eintrag = {"id": uuid.uuid4().hex[:12], "satz": satz, "art": art, "bereiche": [],
               "stichwoerter": [], "schreibend": True, "zug": int(zug),
               "ts": gespraeche.jetzt_ts()}
    _aendern(gid, lambda d: d["zusagen"].append(eintrag))
    return eintrag["id"]


def erledigen(gid, zid, grund: str, zug: int) -> None:
    _aendern(gid, lambda d: d["erledigt"].__setitem__(
        zid, {"grund": grund, "zug": int(zug), "ts": gespraeche.jetzt_ts()}))


def zug_nummer(gid) -> int:
    """Der wievielte Zug (Nachricht von Sasha, auch versteckte Aufträge) das
    Gespräch gerade hat."""
    return sum(1 for n in gespraeche.nachrichten(gid, versteckte=True)
               if n.get("rolle") == "user")


def nachfuehren(gid, zug: int, protokoll, *, nutzer_text: str, belegt, verfall: int):
    """Nach einem Zug: offene Zusagen abhaken (Werkzeug lief / Sasha lehnt
    ab), Bezug vermerken, Verfallene abhaken.

    belegt(bereiche, protokoll, schreibend) -> bool sagt, ob ein Werkzeug sie einlöste
    (von oben hereingegeben: das Werkzeug-Register kennt nur Schicht 3)."""
    import ehrlichkeit_erkennen as erkennen
    nutzer = str(nutzer_text or "").lower()
    ablehnung = erkennen.lehnt_ab(nutzer_text)
    for z in offen(gid):
        if z.get("zug", 0) >= zug or z.get("art"):
            continue            # in diesem Zug erst entstanden / gehört einem Werkzeug
        if belegt(set(z.get("bereiche") or ()), protokoll, z.get("schreibend", True)):
            erledigen(gid, z["id"], "werkzeug", zug)
        elif ablehnung and z.get("zug", 0) == zug - 1:
            erledigen(gid, z["id"], "abgelehnt", zug)
        elif any(w in nutzer for w in z.get("stichwoerter") or ()):
            _aendern(gid, lambda d, i=z["id"]: d["bezug"].__setitem__(i, int(zug)))
        elif zug - z["zuletzt"] >= verfall:
            erledigen(gid, z["id"], "verfallen", zug)
