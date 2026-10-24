# core/abgleich_ics.py
#
# Zwei Fassungen einer .ics-Datei zusammenführen — Termin für Termin (UID +
# RECURRENCE-ID), über die Basis (memory/betrieb/abgleich.md „Kalender").
#
# Warum nicht die Text-Regel: die schriebe bei einem Widerspruch beide
# Fassungen mit ⟪ … ⟫ in die Datei — das ist dann kein iCalendar mehr, und
# vdirsyncer trüge den Bruch zu Google. Eine Datei hält einen Termin (eine
# UID) samt seinen Abweichungen (RECURRENCE-ID, gleiche UID — so schreibt
# ZENTRALE Spannen mit eigener Zeit je Tag). Deshalb je VEVENT:
#
#   nur eine Seite geändert   → die gilt
#   beide gleich geändert     → gut
#   beide verschieden         → der spätere LAST-MODIFIED (sonst DTSTAMP),
#                               bei Gleichstand die Mitte; ein Hinweis
#   gelöscht gegen unverändert→ gelöscht; gelöscht gegen geändert → bleibt
#
# Der Rahmen (VCALENDAR-Kopf, VTIMEZONE …) als Ganzes: geändert gilt, beide
# geändert → die Mitte. Reine Funktionen, Bytes rein, Bytes raus.


class _Teile:
    def __init__(self, vor, termine, reihe, zwischen, nach):
        self.vor, self.termine, self.reihe = vor, termine, reihe
        self.zwischen, self.nach = zwischen, nach

    def rahmen(self):
        return (tuple(self.vor), tuple(self.zwischen), tuple(self.nach))


def _eigenschaft(zeilen, name):
    """Wert einer Eigenschaft der obersten Ebene eines VEVENT (entfaltet)."""
    entfaltet = []
    for z in zeilen[1:-1]:
        roh = z.rstrip("\r\n")
        if roh.startswith((" ", "\t")) and entfaltet:
            entfaltet[-1] += roh[1:]
        else:
            entfaltet.append(roh)
    tiefe = 0
    for e in entfaltet:
        n = _name(e)
        if n == "BEGIN":
            tiefe += 1
        elif n == "END":
            tiefe -= 1
        elif tiefe == 0 and n == name:
            return e.split(":", 1)[1] if ":" in e else ""
    return ""


def _name(zeile):
    return zeile.split(":", 1)[0].split(";", 1)[0].upper()


def zerlegen(roh: bytes) -> _Teile:
    text = roh.decode("utf-8")
    zeilen = text.splitlines(keepends=True)
    if not zeilen or zeilen[0].strip().upper() != "BEGIN:VCALENDAR":
        raise ValueError("kein VCALENDAR")
    vor, zwischen, nach, termine, reihe = [], [], [], {}, []
    i, tiefe, gesehen = 0, 0, False
    while i < len(zeilen):
        z = zeilen[i]
        oben = z.strip().upper()
        if tiefe == 1 and oben == "BEGIN:VEVENT":
            j, t = i, 0
            while j < len(zeilen):
                o = zeilen[j].strip().upper()
                if o.startswith("BEGIN:"):
                    t += 1
                elif o.startswith("END:"):
                    t -= 1
                    if t == 0:
                        break
                j += 1
            if j >= len(zeilen):
                raise ValueError("VEVENT ohne Ende")
            block = zeilen[i:j + 1]
            schluessel = (_eigenschaft(block, "UID"), _eigenschaft(block, "RECURRENCE-ID"))
            if not schluessel[0] or schluessel in termine:
                raise ValueError("VEVENT ohne oder mit doppelter UID")
            termine[schluessel] = "".join(block)
            reihe.append(schluessel)
            zwischen.extend(nach)       # was zwischen zwei Terminen stand
            nach = []
            gesehen = True
            i = j + 1
            continue
        if oben.startswith("BEGIN:") and not z.startswith((" ", "\t")):
            tiefe += 1
        elif oben.startswith("END:") and not z.startswith((" ", "\t")):
            tiefe -= 1
        (nach if gesehen else vor).append(z)
        i += 1
    if not termine:
        raise ValueError("keine Termine")
    return _Teile(vor, termine, reihe, zwischen, nach)


def _zeitpunkt(block: str) -> str:
    for name in ("LAST-MODIFIED", "DTSTAMP"):
        w = "".join(c for c in _eigenschaft(block.splitlines(keepends=True), name) if c.isdigit())
        if w:
            return name + w
    return ""


def _drei(b, l, m):
    """(ergebnis, hinweis|None) für einen Termin. None = gibt es nicht."""
    if l == m:
        return l, None
    if b is not None and l == b:
        return m, None
    if b is not None and m == b:
        return l, None
    if l is None:
        return m, (None if b is None else "hier gelöscht, in der Mitte geändert — bleibt")
    if m is None:
        return l, (None if b is None else "in der Mitte gelöscht, hier geändert — bleibt")
    zl, zm = _zeitpunkt(l), _zeitpunkt(m)
    if zl and zm and zl[:2] == zm[:2] and zl > zm:
        return l, "auf beiden Seiten geändert — die spätere Fassung (von hier) bleibt"
    return m, "auf beiden Seiten geändert — die Fassung aus der Mitte bleibt"


def zusammenfuehren(basis, lokal, mitte):
    """→ (bytes oder None = Datei weg, [hinweise]). ValueError, wenn eine
    Fassung kein lesbares iCalendar ist (dann gilt die Regel „als Ganzes")."""
    tb = zerlegen(basis) if basis is not None else None
    tl, tm = zerlegen(lokal), zerlegen(mitte)
    hinweise = []
    reihe = list(tm.reihe) + [k for k in tl.reihe if k not in tm.termine]
    if tb:
        reihe += [k for k in tb.reihe if k not in reihe]
    termine = []
    for k in reihe:
        b = tb.termine.get(k) if tb else None
        r, h = _drei(b, tl.termine.get(k), tm.termine.get(k))
        if h:
            hinweise.append(f"Termin {k[0]}{' ' + k[1] if k[1] else ''}: {h}")
        if r is not None:
            termine.append(r)
    rb = tb.rahmen() if tb else None
    rahmen = tl if (rb is not None and tm.rahmen() == rb) else tm
    if not termine:
        return None, hinweise + ["alle Termine der Datei gelöscht — Datei weg"]
    text = "".join(rahmen.vor) + "".join(termine) + "".join(rahmen.zwischen) + "".join(rahmen.nach)
    return text.encode("utf-8"), hinweise
