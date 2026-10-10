# core/kachel_felder.py
#
# Die Felder einer Kachel-Art im Katalog (`GET /api/kacheln`,
# memory/system/hub_bauplan.md „Katalog") und ihre Prüfung. Eine App
# beschreibt hier, was man beim Anlegen einer Kachel angeben kann; jede
# Oberfläche baut daraus ihren Dialog SELBST (die TUI:
# tui/bausteine/feld_dialog.py) und der Hub prüft dieselben Regeln noch
# einmal, bevor eine Quelle gefragt wird. So wandert keine Fach-Regel (z. B.
# „höchstens 31 Tage") in eine Oberfläche. 2026-10-10.
#
# Ein Feld (alles JSON):
#   name     Name in der Adresse (Abfrage) und im Bezug der Quelle
#   typ      datum | zahl | wahl | text | bool
#   titel    was die Oberfläche davor schreibt
#   vorgabe  Startwert; bei datum auch „heute" oder „heute+N"
#   hilfe    optional, eine kurze Zeile zum Feld
#   wenn     optional {feld: wert}: das Feld gilt nur, wenn ein anderes Feld
#            diesen Wert hat (sonst fehlt es in der Adresse)
#   werte    nur wahl: [{wert, titel}]
#   dynamisch  nur wahl, optional true: die Werte wechseln zur Laufzeit (z. B.
#            „welche Liste") — die Quelle liefert sie mit `werte(art, name)`,
#            der Katalog trägt sie frisch ein. Geprüft wird dann nur die Form
#            (ein Text); gibt es den Wert nicht mehr, sagt die Quelle „weg"
#            (2026-10-10).
#   grenzen  optional, je Typ:
#              zahl   {min, max}
#              text   {max_laenge}
#              datum  {nicht_vor: <feld>, tage_max: N}  — ab dem genannten
#                     Datumsfeld höchstens N Tage (beide mitgezählt)
# Jedes Feld, das gilt, muss einen Wert haben (text darf leer sein).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import re
from datetime import date, timedelta

from kachel_form import KachelFehler

TYPEN = ("datum", "zahl", "wahl", "text", "bool")


def vorgabe(feld, heute=None):
    """Startwert eines Felds (datum: „heute+N" ausgerechnet)."""
    v = feld.get("vorgabe")
    if feld.get("typ") == "datum" and isinstance(v, str) and v.startswith("heute"):
        heute = heute or date.today()
        rest = v[len("heute"):]
        return (heute + timedelta(days=int(rest or 0))).isoformat()
    return v


def gilt(feld, werte):
    """Gilt das Feld bei diesen Werten (Bedingung `wenn`)?"""
    wenn = feld.get("wenn") or {}
    return all(werte.get(k) == v for k, v in wenn.items())


def _wert(feld, roh):
    """Ein Wert (Text aus der Adresse oder schon getypt) → getypt."""
    typ, titel = feld.get("typ"), feld.get("titel") or feld["name"]
    if typ == "zahl":
        if isinstance(roh, int) and not isinstance(roh, bool):
            return roh
        if isinstance(roh, str) and re.fullmatch(r"-?[0-9]{1,9}", roh.strip()):
            return int(roh)
        raise KachelFehler("%s: eine ganze zahl" % titel)
    if typ == "datum":
        try:
            return date.fromisoformat(str(roh)).isoformat()
        except ValueError:
            raise KachelFehler("%s: datum als JJJJ-MM-TT" % titel)
    if typ == "bool":
        if isinstance(roh, bool):
            return roh
        if str(roh) in ("true", "false"):
            return str(roh) == "true"
        raise KachelFehler("%s: ja oder nein" % titel)
    if typ == "wahl" and feld.get("dynamisch"):
        if not isinstance(roh, str) or not roh.strip():
            raise KachelFehler("%s fehlt" % titel)
        return roh
    if typ == "wahl":
        erlaubt = [w.get("wert") for w in feld.get("werte") or []]
        if roh not in erlaubt:
            raise KachelFehler("%s: eins von %s" % (titel, ", ".join(map(str, erlaubt))))
        return roh
    return str(roh)


def _grenzen(feld, wert, werte):
    g, titel = feld.get("grenzen") or {}, feld.get("titel") or feld["name"]
    typ = feld.get("typ")
    if typ == "zahl":
        if "max" in g and wert > g["max"]:
            raise KachelFehler("höchstens %s %s" % (g["max"], titel))
        if "min" in g and wert < g["min"]:
            raise KachelFehler("%s: mindestens %s" % (titel, g["min"]))
    elif typ == "text" and "max_laenge" in g and len(wert) > g["max_laenge"]:
        raise KachelFehler("%s: höchstens %d zeichen" % (titel, g["max_laenge"]))
    elif typ == "datum" and g.get("nicht_vor") in werte:
        ab = date.fromisoformat(werte[g["nicht_vor"]])
        d = date.fromisoformat(wert)
        if d < ab:
            raise KachelFehler("„%s\" liegt vor „%s\"" % (titel, g["nicht_vor"]))
        if "tage_max" in g and (d - ab).days + 1 > g["tage_max"]:
            raise KachelFehler("höchstens %d tage" % g["tage_max"])


def pruefen(felder, roh):
    """{name: wert} gegen die Felder → getypter Bezug (nur Felder, die
    gelten). Unbekannte Namen sind ein Fehler: eine Adresse, ein Objekt."""
    if not isinstance(roh, dict):
        raise KachelFehler("bezug fehlt")
    namen = {f["name"] for f in felder}
    fremd = sorted(set(roh) - namen)
    if fremd:
        raise KachelFehler("unbekannt: %s" % ", ".join(fremd))
    werte = {}
    for f in felder:                            # Reihenfolge zählt: wenn/nicht_vor zeigen zurück
        if not gilt(f, werte):
            continue
        leer = roh.get(f["name"]) in (None, "") and f.get("typ") != "text"
        if f["name"] not in roh or leer:
            raise KachelFehler("%s fehlt" % (f.get("titel") or f["name"]))
        werte[f["name"]] = _wert(f, roh[f["name"]])
    for f in felder:
        if f["name"] in werte:
            _grenzen(f, werte[f["name"]], werte)
    zuviel = sorted(n for n in roh if n not in werte)
    if zuviel:
        raise KachelFehler("gilt hier nicht: %s" % ", ".join(zuviel))
    return werte


def form_pruefen(felder):
    """Die Felder einer Quelle taugen (für den Katalog und Tests)."""
    for f in felder:
        if not isinstance(f.get("name"), str) or f.get("typ") not in TYPEN:
            raise ValueError("feld ohne name oder mit unbekanntem typ: %r" % (f,))
        if f["typ"] == "wahl" and not f.get("werte") and not f.get("dynamisch"):
            raise ValueError("wahl ohne werte: %r" % (f,))
    return felder
