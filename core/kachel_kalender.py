# core/kachel_kalender.py
#
# Quelle für Kacheln der App `kalender`, Art `ausschnitt`: ein Stück des
# Kalenders von einem Tag bis zu einem Tag, auf einem Desk (Desk View).
# Der Hub (core/kacheln.py) fragt hier an — dieselbe Schnittstelle, die
# später eine ausgezogene Kalender-App über HTTP bedient
# (memory/system/hub_bauplan.md „Kacheln"). 2026-10-10.
#
# Bezug (`ref`), Sasha 2026-10-10:
#   {"modus": "mitlaufend", "tage": 7}   ab heute N Tage, jeden Tag neu
#   {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"}
# Höchstens 31 Tage. Bis 7 Tage eine Woche (eine Spalte je Tag), 8–31 ein
# Monatsraster (Wochen als Zeilen, Mo–So als Spalten).
#
# Gelesen wird NUR über die vorhandenen Lese-Funktionen von core/kalender.py
# (month_view: zeigt nur die sichtbaren Ebenen, wie die Kalender-Ansicht).
# Dieses Modul schreibt nie. Lücke, gemeldet 2026-10-10: es gibt keine
# öffentliche Funktion „Einträge von–bis, nur sichtbare Ebenen" —
# entries_in_range kennt kein only_default_visible. Darum hier bis zu zwei
# month_view-Aufrufe und zuschneiden.
#
# Blättern: `oben` (Zeilen-Versatz in jedem Tag) kommt mit der Anfrage, die
# Antwort sagt, wie weit es geht (`oben_max`). Was nicht passt, zeigt „+N".
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

from datetime import date, timedelta

import kalender
from kachel_form import KachelFehler, KachelZuKlein, kuerzen, stueck

APP = "kalender"
RECHTE = ("lesen",)
# min = kleinste sinnvolle Innengröße (Zellen); die genaue Grenze hängt am
# Bereich und kommt als KachelZuKlein. ttl: ein Kalender ändert sich selten
# von außen, eine Minute reicht (Pull, hub_bauplan.md „Frisch halten").
ARTEN = {"ausschnitt": {"min": (6, 2), "ttl": 60}}
GRENZE_TAGE = 31
WOCHE_BIS = 7
WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
SPALTE_MIN = 6                    # Woche: „09:00 " braucht schon 6
ZELLE_MIN = 5                     # Monat: „12 +3"

# Farbrollen (tui/ansichten/farben.py ROLES). Heute in der Kalender-Farbe
# „kal" — dieselbe wie im Kalender selbst.
R_KOPF, R_HEUTE, R_RAND, R_DRAUSSEN = "dim", "kal", "faint", "faint"
R_ZEIT, R_TITEL, R_GANZ, R_MEHR = "faint", "ink", "span", "acc"


# ── Bezug → Bereich ───────────────────────────────────────────────────

def _datum(s, feld):
    try:
        return date.fromisoformat(str(s))
    except (TypeError, ValueError):
        raise KachelFehler("%s ist kein datum (JJJJ-MM-TT)" % feld)


def bereich(ref, heute=None):
    """Bezug → (von, bis). Mitlaufend rechnet von `heute` aus — jeden Tag
    ein anderer Bereich, ohne dass sich die Datei ändert."""
    heute = heute or date.today()
    if not isinstance(ref, dict):
        raise KachelFehler("bezug fehlt")
    modus = ref.get("modus")
    if modus == "mitlaufend":
        tage = ref.get("tage")
        if isinstance(tage, bool) or not isinstance(tage, int) or tage < 1:
            raise KachelFehler("anzahl tage fehlt")
        if tage > GRENZE_TAGE:
            raise KachelFehler("höchstens %d tage" % GRENZE_TAGE)
        return heute, heute + timedelta(days=tage - 1)
    if modus == "fest":
        von, bis = _datum(ref.get("von"), "von"), _datum(ref.get("bis"), "bis")
        if bis < von:
            raise KachelFehler("„bis\" liegt vor „von\"")
        if (bis - von).days + 1 > GRENZE_TAGE:
            raise KachelFehler("höchstens %d tage" % GRENZE_TAGE)
        return von, bis
    raise KachelFehler("modus muss „mitlaufend\" oder „fest\" sein")


# ── Daten ─────────────────────────────────────────────────────────────

def _tage(von, bis):
    """{iso: [eintrag]} für von..bis, nur sichtbare Ebenen; Ausgefallenes
    und Abgeschaltetes fehlt wie in der Kalender-Ansicht (ohne x)."""
    tage = {}
    monate = {(von.year, von.month), (bis.year, bis.month)}
    for j, m in sorted(monate):
        tage.update(kalender.month_view(date(j, m, 1)).get("days") or {})
    raus = {}
    d = von
    while d <= bis:
        raus[d.isoformat()] = [e for e in tage.get(d.isoformat(), [])
                               if isinstance(e, dict)
                               and not e.get("deaktiviert") and not e.get("ausfall")]
        d += timedelta(days=1)
    return raus


def _posten(eintraege):
    """Einträge eines Tages → [(zeit|None, titel)], Ganztägiges zuerst."""
    ganz = [(None, str(e.get("label") or "?")) for e in eintraege if not e.get("time")]
    zeit = sorted(((str(e["time"]), str(e.get("label") or "?")) for e in eintraege
                   if e.get("time")), key=lambda p: p[0])
    return ganz + zeit


def _stuecke(posten, breite):
    """Ein Posten als Stücke, auf `breite` gekürzt und aufgefüllt."""
    zeit, titel = posten
    if zeit is None:
        return [stueck(kuerzen(titel, breite).ljust(breite), R_GANZ)]
    z = kuerzen(zeit + " ", breite)
    return [stueck(z, R_ZEIT), stueck(kuerzen(titel, breite - len(z)).ljust(breite - len(z)), R_TITEL)]


def _leer(breite, rolle="dim"):
    return [stueck(" " * breite, rolle)]


def _mehr(n, breite):
    return [stueck(kuerzen("+%d" % n, breite).ljust(breite), R_MEHR)]


def _fenster(posten, oben, platz):
    """Sichtbare Posten eines Tages bei Versatz `oben` und `platz` Zeilen:
    (liste, versteckt_unten). Passt nicht alles, kostet „+N" eine Zeile."""
    rest = posten[oben:]
    if len(rest) <= platz:
        return rest, 0
    if platz <= 0:
        return [], len(rest)
    return rest[:platz - 1], len(rest) - (platz - 1)


def _zusammen(zellen, rand):
    """Zellen einer Zeile (je eine Liste Stücke) mit │ dazwischen."""
    zeile = []
    for i, z in enumerate(zellen):
        if i:
            zeile.append(stueck(rand, R_RAND))
        zeile.extend(z)
    return zeile


# ── Woche: eine Spalte je Tag ─────────────────────────────────────────

def _kopf(d, breite):
    lang = "%s %02d.%02d." % (WT[d.weekday()], d.day, d.month)
    if len(lang) <= breite:
        return lang
    kurz = "%s %d" % (WT[d.weekday()], d.day)
    return kurz if len(kurz) <= breite else str(d.day)


def woche(tage, heute, w, h, oben=0):
    """→ (zeilen, oben, oben_max). Kopf mit Wochentag + Datum, darunter je
    Tag die Posten; heute in R_HEUTE."""
    n = len(tage)
    sp = (w - (n - 1)) // n
    if sp < SPALTE_MIN or h < 2:
        raise KachelZuKlein(n * SPALTE_MIN + n - 1, 2)
    platz = h - 1
    posten = [(date.fromisoformat(iso), _posten(e)) for iso, e in tage.items()]
    oben_max = max([0] + [len(p) - platz for _d, p in posten])
    oben = max(0, min(int(oben or 0), oben_max))
    kopf = _zusammen([[stueck(_kopf(d, sp).ljust(sp), R_HEUTE if d == heute else R_KOPF)]
                      for d, _p in posten], "│")
    spalten = []
    for _d, p in posten:
        sicht, versteckt = _fenster(p, oben, platz)
        zellen = [_stuecke(x, sp) for x in sicht]
        if versteckt:
            zellen.append(_mehr(versteckt, sp))
        zellen += [_leer(sp)] * (platz - len(zellen))
        spalten.append(zellen)
    zeilen = [kopf] + [_zusammen([s[j] for s in spalten], "│") for j in range(platz)]
    return zeilen, oben, oben_max


# ── Monat: Wochen als Zeilen, Mo–So als Spalten ───────────────────────

def _tageszahl(d, erster):
    return "%d.%d." % (d.day, d.month) if d.day == 1 or d == erster else "%d" % d.day


def _zahlzeile(d, erster, ist_heute, versteckt, breite):
    """Erste Zeile einer Tageszelle: Zahl links, „+N" rechts (wenn etwas
    nicht passt). Reicht der Platz nicht, schrumpft die Zahl auf den Tag."""
    zahl = _tageszahl(d, erster)
    mehr = "+%d" % versteckt if versteckt else ""
    if mehr and len(zahl) + 1 + len(mehr) > breite:
        zahl = str(d.day)
    zahl = kuerzen(zahl, breite)
    mehr = mehr[:max(0, breite - len(zahl) - 1)] if mehr else ""
    luecke = breite - len(zahl) - len(mehr)
    zeile = [stueck(zahl, R_HEUTE if ist_heute else R_KOPF), stueck(" " * luecke, "dim")]
    if mehr:
        zeile.append(stueck(mehr, R_MEHR))
    return zeile


def monat(tage, heute, w, h, oben=0):
    """→ (zeilen, oben, oben_max). Tage außerhalb des Bereichs bleiben
    leer (leise Zahl), damit das Raster volle Wochen zeigt."""
    von = date.fromisoformat(min(tage))
    bis = date.fromisoformat(max(tage))
    start = von - timedelta(days=von.weekday())
    wochen = ((bis - start).days // 7) + 1
    zw = (w - 6) // 7
    zh = (h - 1) // wochen
    if zw < ZELLE_MIN or zh < 2:
        raise KachelZuKlein(7 * ZELLE_MIN + 6, 1 + 2 * wochen)
    platz = zh - 1
    alle = {iso: _posten(e) for iso, e in tage.items()}
    oben_max = max([0] + [len(p) - platz for p in alle.values()])
    oben = max(0, min(int(oben or 0), oben_max))
    zeilen = [_zusammen([[stueck(kuerzen(t, zw).ljust(zw), R_KOPF)] for t in WT], " ")]
    for wi in range(wochen):
        block = [[] for _ in range(zh)]
        for t in range(7):
            d = start + timedelta(days=wi * 7 + t)
            p = alle.get(d.isoformat())
            if p is None:                                   # außerhalb des Bereichs
                block[0].append([stueck(kuerzen(_tageszahl(d, von), zw).ljust(zw), R_DRAUSSEN)])
                for j in range(1, zh):
                    block[j].append(_leer(zw))
                continue
            sicht = p[oben:oben + platz]
            versteckt = len(p) - oben - len(sicht) if len(p) > oben else 0
            block[0].append(_zahlzeile(d, von, d == heute, versteckt, zw))
            for j in range(1, zh):
                block[j].append(_stuecke(sicht[j - 1], zw) if j - 1 < len(sicht) else _leer(zw))
        zeilen += [_zusammen(z, " ") for z in block]
    return zeilen, oben, oben_max


# ── Schnittstelle für den Hub ─────────────────────────────────────────

def _klartext(tage, von, bis):
    """Rückfall für Programme ohne ZENTRALE (Obsidian): kurz, lesbar."""
    raus = ["Kalender %s–%s" % (von.strftime("%d.%m."), bis.strftime("%d.%m.%Y"))]
    for iso, e in tage.items():
        p = _posten(e)
        if p:
            d = date.fromisoformat(iso)
            raus.append("%s %s: %s" % (WT[d.weekday()], d.strftime("%d.%m."),
                                       ", ".join((z + " " if z else "") + t for z, t in p)))
    return "\n".join(raus)[:2000]


def kachel(art, ref, w, h, oben=0, heute=None):
    """Inhalt der Kachel in w×h Zellen → {zeilen, text, oben, oben_max}."""
    if art not in ARTEN:
        raise KachelFehler("unbekannte art: %s" % art)
    heute = heute or date.today()
    von, bis = bereich(ref, heute)
    tage = _tage(von, bis)
    form = woche if len(tage) <= WOCHE_BIS else monat
    zeilen, oben, oben_max = form(tage, heute, w, h, oben)
    return {"zeilen": zeilen, "text": _klartext(tage, von, bis),
            "oben": oben, "oben_max": oben_max}


def aktion(art, ref, was, heute=None):
    """„oeffnen" → der Kalender an dem Tag, an dem der Ausschnitt beginnt
    (mitlaufend: heute)."""
    if art not in ARTEN:
        raise KachelFehler("unbekannte art: %s" % art)
    if was != "oeffnen":
        raise KachelFehler("unbekannte aktion: %s" % was)
    von, _bis = bereich(ref, heute)
    return {"zeige": {"ansicht": "kalender", "ziel": von.isoformat()}}
