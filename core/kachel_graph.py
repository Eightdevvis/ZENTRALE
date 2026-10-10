# core/kachel_graph.py
#
# Quelle für Kacheln der App `graph` (Lifestyle-Graphen), Art `verlauf`: die
# letzten N Tage eines Graphen als Balken aus Blockzeichen ▁▂▃▄▅▆▇█, oben
# Name, Einheit und letzter Wert, unten Kleinst- und Höchstwert. Der Hub
# (core/kacheln.py) fragt hier an — dieselbe Schnittstelle, die später eine
# ausgezogene Graph-App über HTTP bedient (memory/system/hub_bauplan.md
# „Kacheln"). 2026-10-10.
#
# Bezug als Adresse, z. B. zentrale://graph/verlauf?graph=g_schlaf&tage=14
# Der Graph selbst hat die Adresse zentrale://graph/<gid> — die kommt bei
# „oeffnen" zurück.
#
# Typen (core/graphs.py) wie im Graph-Werkzeug der TUI, mit denselben
# Helfern (core/graph_reihen.py): number und scale als Zahl (scale fest
# 0–5, damit eine 3 immer gleich hoch ist), time als Uhrzeit, period als
# Dauer der Spanne. Je Tag eine Spalte, heute ganz rechts; passen mehr Tage
# als Spalten, steht eine Spalte für mehrere Tage (Mittel). Ein Tag ohne
# Wert ist ein leiser Punkt.
#
# NUR LESEN: graphs.list_graphs() und graphs.read_values() lesen nur.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

from datetime import date, timedelta

import adressen
import graph_reihen
import graphs
from kachel_form import KachelFehler, KachelWeg, kuerzen, stueck

APP = "graph"
RECHTE = ("lesen",)
TAGE_GRENZE = 365
SKALA_OBEN = 5                    # scale: 1–5 Bewertung
LUECKE = "·"

ARTEN = {"verlauf": {
    "titel": "graph",
    "min": (12, 2),
    "bevorzugt": (30, 6),
    "ttl": 120,                   # Werte kommen höchstens ein paarmal am Tag
    "felder": [
        {"name": "graph", "typ": "wahl", "titel": "graph", "dynamisch": True,
         "hilfe": "←→ blättert durch die graphen"},
        {"name": "tage", "typ": "zahl", "titel": "tage", "vorgabe": 14,
         "grenzen": {"min": 2, "max": TAGE_GRENZE}, "hilfe": "die letzten tage bis heute"},
    ],
}}

# Farbrollen (core/farbrollen.py): nur die Bedeutung.
R_KOPF, R_EINHEIT, R_LETZT = "kopf", "leise", "betont"
R_BALKEN, R_HEUTE, R_LUECKE, R_FUSS, R_LEER = "text", "heute", "leise", "leise", "leise"


# ── Daten ─────────────────────────────────────────────────────────────

def _graph(gid):
    for g in graphs.list_graphs():
        if isinstance(g, dict) and g.get("id") == gid:
            return g
    raise KachelWeg(gid)


def werte(art, name):
    """Die Graphen zur Wahl (Katalog, Feld `graph`): [{wert, titel}]."""
    if art != "verlauf" or name != "graph":
        return []
    return [{"wert": str(g["id"]), "titel": str(g.get("name") or g["id"])}
            for g in graphs.list_graphs() if isinstance(g, dict) and g.get("id")]


def _pruefen(art, ref):
    if art not in ARTEN:
        raise KachelFehler("unbekannte art: %s" % art)
    if not isinstance(ref, dict) or not isinstance(ref.get("graph"), str):
        raise KachelFehler("graph fehlt")
    tage = ref.get("tage")
    if isinstance(tage, bool) or not isinstance(tage, int) or not 2 <= tage <= TAGE_GRENZE:
        raise KachelFehler("tage: 2 bis %d" % TAGE_GRENZE)
    return ref["graph"], tage


def tageswerte(g, rows, tage, heute):
    """→ [(datum, zahl|None)] für die letzten `tage` Tage bis heute; je Tag
    der zuletzt eingetragene Wert (period: die Dauer)."""
    von = heute - timedelta(days=tage - 1)
    je_tag = {}
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        try:
            d = date.fromisoformat(str(e.get("date")))
        except ValueError:
            continue
        v = graph_reihen.wert(g.get("type"), e)
        if von <= d <= heute and v is not None:
            je_tag[d] = v
    return [(von + timedelta(days=i), je_tag.get(von + timedelta(days=i)))
            for i in range(tage)]


# ── Zeichnen ──────────────────────────────────────────────────────────

def spalten(tag_werte, breite):
    """Tage → Spalten: [(zahl|None, enthaelt_heute)]. Passen alle Tage, eine
    Spalte je Tag (breitere Spalten, wenn Platz ist, bis 3); sonst steht
    eine Spalte für mehrere Tage (Mittel der eingetragenen)."""
    n = len(tag_werte)
    if n <= breite:
        je = max(1, min(3, breite // n))
        raus = []
        for i, (_d, v) in enumerate(tag_werte):
            raus += [(v, i == n - 1)] * je
        return raus
    raus = []
    for c in range(breite):
        stueck_ = tag_werte[c * n // breite:(c + 1) * n // breite]
        da = [v for _d, v in stueck_ if v is not None]
        raus.append((sum(da) / len(da) if da else None, c == breite - 1))
    return raus


def _spanne(g, zahlen):
    if g.get("type") == "scale":
        return 0.0, float(SKALA_OBEN)
    return min(zahlen), max(zahlen)


def _achtel(v, lo, hi, zeilen):
    """Höhe eines Balkens in Achteln (mindestens eins: auch der kleinste
    Wert bleibt sichtbar)."""
    gesamt = zeilen * 8
    if hi <= lo:
        return max(1, gesamt // 2)
    anteil = (min(max(v, lo), hi) - lo) / (hi - lo)
    return max(1, min(gesamt, 1 + round(anteil * (gesamt - 1))))


def balken(g, spalten_, zeilen):
    """Spalten → `zeilen` Zeilen aus Stücken (oben zuerst)."""
    zahlen = [v for v, _h in spalten_ if v is not None]
    lo, hi = _spanne(g, zahlen) if zahlen else (0.0, 1.0)
    hoehen = [None if v is None else _achtel(v, lo, hi, zeilen) for v, _h in spalten_]
    raus = []
    for r in range(zeilen):
        unten = zeilen - 1 - r                 # wie viele Zeilen darunter
        zeile = []
        for (v, heute), hoch in zip(spalten_, hoehen):
            if hoch is None:
                zeile.append(stueck(LUECKE if unten == 0 else " ", R_LUECKE))
                continue
            fuell = hoch - unten * 8
            z = "█" if fuell >= 8 else (" " if fuell <= 0 else graph_reihen.BLOECKE[fuell - 1])
            zeile.append(stueck(z, R_HEUTE if heute else R_BALKEN))
        raus.append(_zusammen(zeile))
    return raus


def _zusammen(zeile):
    """Nachbarn mit gleicher Rolle zu einem Stück (kleinere Antwort)."""
    raus = []
    for text, rolle in zeile:
        if raus and raus[-1][1] == rolle:
            raus[-1][0] += text
        else:
            raus.append([text, rolle])
    return raus


def _kopf(g, letzt, w):
    """Name (+ Einheit) links, letzter Wert rechts."""
    rechts = kuerzen(letzt, max(0, w // 2)) if letzt else ""
    einheit = " " + str(g["unit"]) if g.get("unit") and g.get("type") == "number" else ""
    platz = w - len(rechts) - (1 if rechts else 0)
    name = kuerzen(str(g.get("name") or g.get("id")), max(1, platz))
    einheit = einheit if len(name) + len(einheit) <= platz else ""
    zeile = [stueck(name, R_KOPF)]
    if einheit:
        zeile.append(stueck(einheit, R_EINHEIT))
    luecke = w - len(name) - len(einheit) - len(rechts)
    if luecke > 0:
        zeile.append(stueck(" " * luecke, R_LEER))
    if rechts:
        zeile.append(stueck(rechts, R_LETZT))
    return zeile


def _fuss(g, zahlen, von, heute, w):
    links = "min %s  max %s" % (graph_reihen.wert_text(g, min(zahlen)),
                                graph_reihen.wert_text(g, max(zahlen)))
    rechts = "%s–%s" % (von.strftime("%d.%m."), heute.strftime("%d.%m."))
    if len(links) + 2 + len(rechts) > w:
        return [stueck(kuerzen(links, w), R_FUSS)]
    return [stueck(links + " " * (w - len(links) - len(rechts)) + rechts, R_FUSS)]


def bild(g, rows, tage, w, h, heute):
    """→ zeilen in w×h Zellen. h=2: Kopf + eine Zeile Balken; ab h=3
    zusätzlich unten min/max."""
    tw = tageswerte(g, rows, tage, heute)
    zahlen = [v for _d, v in tw if v is not None]
    da = [e for e in rows if isinstance(e, dict) and e.get("value") is not None
          and str(e.get("date", "")) <= heute.isoformat()]
    letzt = graph_reihen.letzter(g, sorted(da, key=lambda e: str(e.get("date", "")))) \
        if zahlen else ""
    zeilen = [_kopf(g, letzt, w)]
    if not zahlen:
        return zeilen + [[stueck(kuerzen("keine werte in %d tagen" % tage, w), R_LEER)]]
    hoehe = h - 1 if h < 3 else h - 2
    sp = spalten(tw, w)
    rand = w - len(sp)                         # heute steht ganz rechts
    zeilen += [([stueck(" " * rand, R_LEER)] if rand > 0 else []) + z
               for z in balken(g, sp, hoehe)]
    if h >= 3:
        zeilen.append(_fuss(g, zahlen, tw[0][0], heute, w))
    return zeilen


def _klartext(g, rows, tage, heute):
    """Rückfall für Programme ohne ZENTRALE (Obsidian): kurz, lesbar."""
    tw = tageswerte(g, rows, tage, heute)
    zahlen = [v for _d, v in tw if v is not None]
    kopf = "%s, letzte %d tage" % (g.get("name") or g.get("id"), tage)
    if not zahlen:
        return kopf + ": keine werte"
    return "%s: %s (min %s, max %s)" % (kopf, graph_reihen.blockspark(zahlen),
                                        graph_reihen.wert_text(g, min(zahlen)),
                                        graph_reihen.wert_text(g, max(zahlen)))


# ── Schnittstelle für den Hub ─────────────────────────────────────────

def kachel(art, ref, w, h, oben=0, heute=None):
    """Inhalt der Kachel in w×h Zellen → {zeilen, text, oben, oben_max}.
    Ein Verlauf blättert nicht (oben bleibt 0)."""
    gid, tage = _pruefen(art, ref)
    g = _graph(gid)
    heute = heute or date.today()
    rows = graphs.read_values(gid)
    return {"zeilen": bild(g, rows, tage, w, h, heute), "oben": 0, "oben_max": 0,
            "text": _klartext(g, rows, tage, heute)}


def bevorzugt(art, ref):
    """Bevorzugte Innengröße → (w, h): bis 30 Tage zwei Spalten je Tag,
    darüber eine; zwischen 24 und 60 breit, 6 hoch."""
    _gid, tage = _pruefen(art, ref)
    w = tage * 2 if tage * 2 <= 60 else tage
    return max(24, min(60, w)), 6


def aktion(art, ref, was):
    """„oeffnen" → die Adresse des Graphen, zentrale://graph/<gid>."""
    gid, _tage = _pruefen(art, ref)
    if was != "oeffnen":
        raise KachelFehler("unbekannte aktion: %s" % was)
    _graph(gid)
    return {"zeige": {"adresse": adressen.bauen(APP, [gid])}}
