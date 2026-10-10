"""Gruppen im Monat (Ansicht B) — reine Funktionen, kein curses.

Sasha, 10.10.2026: „in der monatsansicht seh ich einfach lieber uni uni uni
statt jeden tag welche fächer genau, dafür ist die wochenansicht" — und als
Form „Uni 08:30–16:00". Einträge EINES Tages mit derselben Gruppe
(iCalendar CATEGORIES, im Kern core/kalender_kategorie.py; die API liefert
`kategorie`, bei eigenen Namen `kategorie_name`) werden in B zu einer Zeile:
erste Anfangszeit bis letztes Ende, Name der Gruppe. A und C zeigen weiter
jedes Fach.

Die zusammengefasste Zeile ist ein normaler Eintrag der Liste (wie aus
kalender_ansichten._tag_eintraege), nur mit `gruppe` und `glieder`; ihr
`roh` ist ein kleines Dict mit `gruppe: True`, `tag` und den API-Einträgen
der Glieder. Die Bedienung wählt sie per Tab wie jeden Termin, Enter zeigt
die Glieder (kalender_werkzeuge.details_gruppe).
"""
from __future__ import annotations

KEINE = "keine"
CUSTOM = "custom"
# Anzeigenamen des Katalogs (core/kalender_kategorie.KATEGORIEN). Rückfall,
# falls das Backend nicht antwortet; die Bedienung lädt die echten Namen von
# GET /api/calendar/kategorien (namen_setzen), damit ein neuer Eintrag im
# Kern ohne TUI-Änderung erscheint.
NAMEN = {"uni": "Uni", "arbeit": "Arbeit"}


def namen_setzen(katalog) -> None:
    """[{schluessel, name}] von /api/calendar/kategorien übernehmen (ohne
    keine/custom — das sind keine Gruppen, sondern Schalter)."""
    if not isinstance(katalog, list):
        return
    neu = {k["schluessel"]: k["name"] for k in katalog
           if isinstance(k, dict) and isinstance(k.get("schluessel"), str)
           and isinstance(k.get("name"), str) and k["schluessel"] not in (KEINE, CUSTOM)}
    if neu:
        NAMEN.clear()
        NAMEN.update(neu)


def schluessel(roh) -> str | None:
    """Fester Schlüssel der Gruppe eines API-Eintrags („uni", bei eigenen
    Namen „custom:<name klein>") oder None (keine Gruppe)."""
    if not isinstance(roh, dict):
        return None
    k = roh.get("kategorie")
    if not isinstance(k, str) or not k or k == KEINE:
        return None
    if k == CUSTOM:
        n = (roh.get("kategorie_name") or "").strip()
        return "custom:" + n.casefold() if n else None
    return k


def anzeige(roh) -> str | None:
    """Der Name der Gruppe („Uni", der eigene Name)."""
    k = schluessel(roh)
    if k is None:
        return None
    if k.startswith("custom:"):
        return (roh.get("kategorie_name") or "").strip()
    return NAMEN.get(k) or k.capitalize()


def farb_schluessel(roh) -> str | None:
    """Schlüssel in der festen Farbtabelle (kalender_ansichten.FARBTABELLE):
    „gruppe:uni" — so bekommt eine Gruppe ihre Farbe über dieselbe Vergabe
    wie die Kurse, ohne einem Kurs den Platz wegzunehmen."""
    k = schluessel(roh)
    return "gruppe:" + k if k else None


def _hm(m) -> str:
    return "%02d:%02d" % (m // 60, m % 60)


def zusammenfassen(eintraege: list) -> list:
    """Normierte Einträge eines Tages → dieselbe Liste, nur dass alle mit
    Uhrzeit und gleicher Gruppe EINE Zeile sind (an der Stelle des ersten).
    Spannen, Ganztägiges und Ausgeschaltetes bleiben einzeln: ein Balken
    oder ein „✗" sagt mehr als der Gruppenname."""
    gruppen: dict = {}
    for t in eintraege:
        k = schluessel(t.get("roh"))
        if k and not t["spanne"] and not t["aus"] and t["start"] is not None:
            gruppen.setdefault(k, []).append(t)
    if not gruppen:
        return list(eintraege)
    out, gesetzt = [], set()
    for t in eintraege:
        k = schluessel(t.get("roh"))
        glieder = gruppen.get(k) if k else None
        if not glieder or not any(t is g for g in glieder):
            out.append(t)
            continue
        if k in gesetzt:
            continue
        gesetzt.add(k)
        out.append(_gruppe(k, glieder))
    return out


def _gruppe(k: str, glieder: list) -> dict:
    erst = glieder[0]
    start = min(t["start"] for t in glieder)
    enden = [t["ende"] if t["ende"] is not None else t["start"] for t in glieder]
    ende = max(enden)
    ende = ende if ende > start else None
    name = anzeige(erst["roh"]) or k
    roh = {"gruppe": True, "schluessel": k, "label": name, "tag": erst["tag"],
           "time": _hm(start), "ende": _hm(ende) if ende is not None else None,
           "kategorie": erst["roh"].get("kategorie"),
           "kategorie_name": erst["roh"].get("kategorie_name"),
           "glieder": [t["roh"] for t in glieder]}
    return {**erst, "label": name, "start": start, "ende": ende,
            "routine": False, "aus": False,
            "unv": all(t["unv"] for t in glieder),
            "key": ("gruppe", k, erst["tag"]),
            "gruppe": k, "glieder": glieder, "roh": roh}


def selbe(a, b) -> bool:
    """Ist `a` der gewählte Eintrag `b`? Echte Einträge per Identität (wie
    überall in den Ansichten); eine Gruppe wird bei jedem Zeichnen neu
    gebaut, also per Schlüssel und Tag."""
    if a is b:
        return True
    return (isinstance(a, dict) and isinstance(b, dict) and bool(a.get("gruppe"))
            and bool(b.get("gruppe")) and a.get("schluessel") == b.get("schluessel")
            and a.get("tag") == b.get("tag"))


def text(t: dict, breite: int) -> str:
    """„08:30–16:00 Uni", wird es eng „08:30–16 Uni", dann „08:30 Uni",
    zuletzt nur der Name."""
    s, e, name = t["start"], t["ende"], t["label"]
    kand = []
    if e is not None:
        kand.append("%s–%s %s" % (_hm(s), _hm(e), name))
        if e % 60 == 0:
            kand.append("%s–%02d %s" % (_hm(s), e // 60, name))
    kand.append("%s %s" % (_hm(s), name))
    for k in kand:
        if len(k) <= breite:
            return k
    return name
