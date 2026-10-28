# core/abgleich_vorschlaege.py
#
# Was ein fremder Knoten (das Handy) VORSCHLAGEN darf — Dateien, die nicht
# ihm allein gehören, die ein Rechner aber aus seinem Eingang übernimmt,
# solange nichts dagegen spricht (memory/betrieb/abgleich_fremde_knoten.md, „Format für
# fremde Knoten“). Die eigenen Dateien eines Knotens (seine .jsonl …) stehen
# in abgleich.eigene_datei; hier nur die Vorschläge:
#
#   data/gespraeche/<id>/kopf.json      Kopf eines NEUEN Gesprächs — gilt
#                                       nur, solange die Mitte keinen hat
#   data/kalender/<ebene>/<uid>.ics     ein Termin (kalender_vorschlag_annehmen):
#                                       neu (seit 2026-10-28), geändert, einzelne
#                                       Vorkommen aus/an, Ebene gewechselt,
#                                       gelöscht (seit 2026-10-29)
#
# Ein Rechner führt die Mitte zusammen, das Handy nicht. Damit ein geänderter
# Termin trotzdem nie etwas in der Cloud überschreibt (Sasha, 28.10.2026:
# „Was in der Cloud ist, darf nie einfach so überschrieben werden“), sagt das
# Handy, WELCHE Fassung der Mitte es gesehen hat (`basis_sha`, der sha aus
# inhalt.enc; besser dazu die Fassung selbst, `basis`). Dann je VEVENT
# (UID + RECURRENCE-ID) drei Wege:
#
#   nur das Handy geändert   → die Fassung vom Handy (was es nicht kennt —
#                              DESCRIPTION, fremde VALARMs, Google-Felder —
#                              bleibt aus der Mitte, wie VERWALTET in
#                              kalender_ics_abbildung.zusammenfuehren)
#   nur die Mitte geändert   → die Mitte
#   beide verschieden        → ABGELEHNT, nichts geschrieben, beide bleiben
#                              (nie „der Spätere gewinnt“ — anders als zwischen
#                              zwei Rechnern in abgleich_ics)
#
# Löschen nur ausdrücklich (`loeschen: true` + `basis_sha`), nie, weil eine
# Datei fehlt. Reine Funktionen: Pfade und Bytes rein, Entscheidung raus.

import hashlib
import re
from datetime import datetime

import abgleich_ics
import dateien

_EBENE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")   # wie kalender_ics.ordner_fuer
_SHA = re.compile(r"^[0-9a-f]{64}$")

ANGENOMMEN, ABGELEHNT, ERLEDIGT = "angenommen", "abgelehnt", "erledigt"


def ist_kopf(rel: str) -> bool:
    """Der Kopf eines Gesprächs (data/gespraeche/<id>/kopf.json)."""
    teile = rel.split("/")
    return (len(teile) == 4 and rel.startswith("data/gespraeche/")
            and teile[2][:1] not in ("_", ".") and teile[3] == "kopf.json")


def ist_kalender(rel: str) -> bool:
    """Ein Termin im Kalender-Ordner (data/kalender/<ebene>/<name>.ics)."""
    teile = rel.split("/")
    return (len(teile) == 4 and teile[0] == "data" and teile[1] == "kalender"
            and bool(_EBENE.match(teile[2])) and teile[3].endswith(".ics")
            and not teile[3].startswith("."))


def ist_vorschlag(rel: str) -> bool:
    return ist_kopf(rel) or ist_kalender(rel)


def sha(b):
    return hashlib.sha256(b).hexdigest() if b is not None else None


class Vorschlag:
    """Ein Umschlag aus dem Eingang. inhalt = die ganze .ics (None beim
    Löschen); basis_sha = sha256 der Fassung der Mitte, die der Knoten
    gesehen hat; basis = diese Fassung selbst (wahlweise); umschlag = sha256
    des entschlüsselten Umschlags (die Quittung nennt ihn)."""

    def __init__(self, rel, inhalt=None, loeschen=False, basis_sha=None, basis=None,
                 knoten="", umschlag=""):
        self.rel, self.inhalt, self.loeschen = rel, inhalt, bool(loeschen)
        self.basis_sha = basis_sha if isinstance(basis_sha, str) and _SHA.match(basis_sha) else None
        self.basis = basis if self.basis_sha and sha(basis) == self.basis_sha else None
        self.knoten, self.umschlag = knoten, umschlag


class Entscheid:
    """ergebnis: angenommen | abgelehnt | erledigt (nichts mehr zu tun).
    schreiben: {rel: bytes | None=löschen} — was in die Sicht der Mitte geht."""

    def __init__(self, ergebnis, grund=None, schreiben=None):
        self.ergebnis, self.grund, self.schreiben = ergebnis, grund, schreiben or {}

    @property
    def ja(self):
        return self.ergebnis == ANGENOMMEN


def _nein(grund):
    return Entscheid(ABGELEHNT, grund)


def _uids(roh: bytes) -> set:
    """Die UIDs einer .ics (leer, wenn sie sich nicht lesen lässt)."""
    try:
        return {uid for uid, _rid in abgleich_ics.zerlegen(roh).termine}
    except (ValueError, UnicodeDecodeError):
        return set()


def _ebene_da(ebene, mitte):
    return any(r.startswith(f"data/kalender/{ebene}/") for r in mitte)


# ── Vergleichen und Übernehmen je VEVENT ───────────────────────────────

def _kanon(block):
    """Gleich im Sinn des Termins: entfaltet, ohne Zeilenende, ohne DTSTAMP
    (den schreibt jeder Export neu), Reihenfolge egal. None bleibt None."""
    if block is None:
        return None
    zeilen = []
    for z in block.splitlines():
        if z.startswith((" ", "\t")) and zeilen:
            zeilen[-1] += z[1:]
        elif z.strip():
            zeilen.append(z.rstrip())
    return tuple(sorted(z for z in zeilen if abgleich_ics._name(z) != "DTSTAMP"))


def _gleich(a, b):
    return _kanon(a) == _kanon(b)


def _rahmen_text(t):
    return "".join(t.vor) + "".join(t.zwischen) + "".join(t.nach)


def _event(block):
    from icalendar import Calendar
    if not block.endswith("\n"):
        block += "\r\n"
    kal = Calendar.from_ical("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//ZENTRALE//Abgleich//DE\r\n"
                             + block + "END:VCALENDAR\r\n")
    return kal.walk("VEVENT")[0]


def _aus_angleichen(ev):
    """X-ZENTRALE-AUS hält die genaue Liste der abgeschalteten Vorkommen; jedes
    Datum darin steht auch als EXDATE. Hat das Handy ein EXDATE entfernt (ein
    Vorkommen wieder an), muss es auch aus X-ZENTRALE-AUS — sonst läse
    ZENTRALE es weiter als aus. Ein neues EXDATE ohne Eintrag liest ZENTRALE
    ohnehin als aus (kalender_ics_abbildung._routine_lesen)."""
    import kalender_ics_abbildung as abb
    x = abb._xdekodieren(ev.get(abb.X_AUS))
    if not isinstance(x, list):
        return
    ex = set()
    for liste in abb._liste(ev.get("EXDATE")):
        for v in getattr(liste, "dts", []):
            w = abb._lokal(v.dt)
            ex.add(w.date() if isinstance(w, datetime) else w)
    neu = [a for a in x if not isinstance(a, str) or abb._datum(a) is None or abb._datum(a) in ex]
    if neu != x:
        ev.pop(abb.X_AUS, None)
        ev.add(abb.X_AUS, abb._xkodieren(neu))


def _uebernehmen(p, m, rid):
    """Die Fassung vom Handy, ergänzt um alles aus der Mitte, was ZENTRALE
    nicht verwaltet und das Handy nicht mitgeschickt hat (wie VERWALTET in
    kalender_ics_abbildung.zusammenfuehren: DESCRIPTION, fremde VALARMs,
    Google-Felder, X-ZENTRALE-* — ein Knoten, der sie beim Lesen verliert,
    löscht sie so nicht). Dazu X-ZENTRALE-AUS passend zu EXDATE."""
    import kalender_ics_abbildung as abb
    ev = _event(p)
    if m is not None:
        alt = _event(m)
        verwaltet = abb.VERWALTET_ABWEICHUNG if rid else abb.VERWALTET
        schon = {n for n, _w in ev.property_items(recursive=False)}
        for n, w in alt.property_items(recursive=False):
            if n in ("BEGIN", "END") or n in verwaltet or n in schon:
                continue
            ev.add(n, w)
        if not ev.subcomponents:
            for sub in alt.subcomponents:
                ev.add_component(sub)
    if not rid:
        _aus_angleichen(ev)
    return ev.to_ical().decode("utf-8")


def dreiweg(basis: bytes, vorschlag: bytes, mitte: bytes):
    """→ (bytes, []) oder (None, [Widersprüche]). Je VEVENT: nur der Vorschlag
    geändert → er (ergänzt, _uebernehmen); nur die Mitte → sie; beide
    verschieden → Widerspruch (dann wird NICHTS übernommen)."""
    tb, tp, tm = (abgleich_ics.zerlegen(x) for x in (basis, vorschlag, mitte))
    reihe = list(tm.reihe) + [k for k in tp.reihe if k not in tm.termine]
    reihe += [k for k in tb.reihe if k not in reihe]
    termine, widerspruch = [], []
    for k in reihe:
        b, p, m = tb.termine.get(k), tp.termine.get(k), tm.termine.get(k)
        name = k[0] + (f" am {k[1]}" if k[1] else "")
        if _gleich(p, m) or _gleich(p, b):
            r = m
        elif _gleich(m, b):
            r = None if p is None else _uebernehmen(p, m, k[1])
        else:
            widerspruch.append(f"{name}: am Handy und in der Mitte verschieden geändert"
                               if p is not None and m is not None else
                               f"{name}: auf der einen Seite gelöscht, auf der anderen geändert")
            continue
        if r is not None:
            termine.append(r)
    if widerspruch:
        return None, widerspruch
    if _gleich(_rahmen_text(tp), _rahmen_text(tb)):
        rahmen = tm
    elif _gleich(_rahmen_text(tm), _rahmen_text(tb)):
        rahmen = tp
    else:
        rahmen = tm
    text = "".join(rahmen.vor) + "".join(termine) + "".join(rahmen.zwischen) + "".join(rahmen.nach)
    return text.encode("utf-8"), []


def _schon_drin(vorschlag: bytes, mitte: bytes) -> bool:
    """Steht alles aus dem Vorschlag schon in der Mitte (übernommen, nur die
    Quittung fehlt — oder dieselbe Änderung kam auf anderem Weg)?"""
    tp, tm = abgleich_ics.zerlegen(vorschlag), abgleich_ics.zerlegen(mitte)
    if set(tp.termine) != set(tm.termine):
        return False
    return all(_gleich(_uebernehmen(p, tm.termine[k], k[1]), tm.termine[k])
               for k, p in tp.termine.items())


# ── Die eine Regel ─────────────────────────────────────────────────────

def kalender_vorschlag_annehmen(v: Vorschlag, mitte: dict, geloescht: dict,
                                basis: dict | None = None) -> Entscheid:
    """Darf der Termin-Vorschlag `v` aus einem Eingang in die Mitte?

    mitte     = {rel: bytes} — was das Inhaltsverzeichnis gerade nennt
    geloescht = die Grabsteine aus inhalt.enc
    basis     = die Basis dieses Rechners {rel: bytes}: liefert die Fassung,
                die das Handy gesehen hat, falls es nur `basis_sha` schickt

    Fälle (memory/betrieb/abgleich_fremde_knoten.md „Termine vom Handy“):
    neu · geändert · Vorkommen aus/an (= geändert: EXDATE + X-ZENTRALE-AUS) ·
    Ebene gewechselt (dieselbe UID unter anderer Ebene: alte Datei weg, neue
    da, in EINEM Stand) · gelöscht (`loeschen`). Widerspruch → abgelehnt,
    nichts überschrieben."""
    rel = v.rel
    ebene = rel.split("/")[2]
    if v.loeschen:
        if rel not in mitte:
            return Entscheid(ERLEDIGT) if rel in geloescht else _nein("den Termin gibt es nicht")
        if not v.basis_sha:
            return _nein("Löschen braucht basis_sha (welche Fassung gesehen wurde)")
        if sha(mitte[rel]) != v.basis_sha:
            return _nein("inzwischen in der Mitte geändert — nicht gelöscht")
        return Entscheid(ANGENOMMEN, schreiben={rel: None})

    from icalendar import Calendar
    try:
        teile = abgleich_ics.zerlegen(v.inhalt or b"")
        Calendar.from_ical(v.inhalt)
    except Exception:       # noqa: BLE001 — alles Unlesbare ist dasselbe: kein Termin
        return _nein("kein lesbarer Termin")
    uids = {uid for uid, _rid in teile.termine}
    if len(uids) != 1:
        return _nein("eine Datei hält genau einen Termin (eine UID)")
    uid = uids.pop()
    if (uid, "") not in teile.termine:
        return _nein("der Hauptteil des Termins fehlt (Löschen nur mit loeschen)")
    orte = [r for r, roh in mitte.items() if ist_kalender(r) and uid in _uids(roh)]

    if not orte:                                     # ── neu
        if rel in mitte:
            return _nein("unter diesem Namen liegt ein anderer Termin")
        if rel in geloescht:
            if v.basis_sha:
                return _nein("in der Mitte gelöscht, am Handy geändert — nicht wiederhergestellt")
            return Entscheid(ERLEDIGT)              # alter neuer Vorschlag, längst gelöscht
        if not _ebene_da(ebene, mitte):
            return _nein(f"die Ebene „{ebene}“ gibt es nicht")
        if rel.rsplit("/", 1)[1] != dateien.sicherer_name(uid) + ".ics":
            return _nein("der Dateiname passt nicht zur UID")
        return Entscheid(ANGENOMMEN, schreiben={rel: v.inhalt})

    if len(orte) > 1:
        return _nein("diese UID liegt in der Mitte mehrfach")
    alt = orte[0]
    m = mitte[alt]
    if alt != rel:                                   # ── Ebene gewechselt
        if alt.split("/")[2] == ebene:
            return _nein("diesen Termin gibt es schon unter einem anderen Namen")
        if rel in mitte:
            return _nein("am Ziel liegt schon eine andere Datei")
        if not _ebene_da(ebene, mitte):
            return _nein(f"die Ebene „{ebene}“ gibt es nicht")
        if rel.rsplit("/", 1)[1] != dateien.sicherer_name(uid) + ".ics":
            return _nein("der Dateiname passt nicht zur UID")
    elif _schon_drin(v.inhalt, m):
        return Entscheid(ERLEDIGT)

    if not v.basis_sha:
        return _nein("diesen Termin gibt es schon — Ändern braucht basis_sha "
                     "(welche Fassung gesehen wurde), nichts überschrieben")
    if sha(m) == v.basis_sha:
        b = m
    elif v.basis is not None:
        b = v.basis
    elif basis and sha(basis.get(alt)) == v.basis_sha:
        b = basis[alt]
    else:
        return _nein("inzwischen in der Mitte geändert, und die Fassung, die das Handy "
                     "sah, kenne ich nicht — nichts überschrieben")
    try:
        neu, widerspruch = dreiweg(b, v.inhalt, m)
        if neu is not None:
            Calendar.from_ical(neu)
    except Exception:       # noqa: BLE001
        return _nein("Zusammenführen ergab keinen lesbaren Termin — nichts überschrieben")
    if widerspruch:
        return _nein("Widerspruch — " + "; ".join(widerspruch[:3]))
    if alt == rel:
        return Entscheid(ERLEDIGT) if neu == m else Entscheid(ANGENOMMEN, schreiben={rel: neu})
    return Entscheid(ANGENOMMEN, schreiben={rel: neu, alt: None})
