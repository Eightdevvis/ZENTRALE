# core/kachel_fokus.py
#
# Quelle für Kacheln der App `fokus` (Listen), Art `liste`: eine Liste mit
# ihren Punkten, abgehakt oder offen, Unterpunkte eingerückt, oben der
# Fortschritt (erledigt/alle). Der Hub (core/kacheln.py) fragt hier an —
# dieselbe Schnittstelle, die später eine ausgezogene Listen-App über HTTP
# bedient (memory/system/hub_bauplan.md „Kacheln"). 2026-10-10.
#
# Bezug als Adresse, z. B.
#   zentrale://fokus/liste?erledigte=false&liste=l_einkauf&tiefe=3
# Die Liste selbst hat die Adresse zentrale://fokus/<liste> (ein Eintrag:
# zentrale://fokus/<liste>/<eintrag>) — die kommt bei „oeffnen" zurück.
#
# Gezeigt wird wie in der Listen-Ansicht der TUI (tui/ansichten/fokus.py):
# dieselben Helfer (core/listen_baum.py) — offen zuerst, der Fokus oben,
# was kaum noch Saft braucht, weiter oben. Erledigtes nur, wenn gewünscht
# (dann hinter dem Offenen derselben Ebene).
#
# NUR LESEN (Sasha 2026-10-10: Enter/`o` = nur öffnen). Gelesen wird über
# lists.read_lists(), das garantiert nicht schreibt — auch nicht die
# einmalige »week«-Migration. Die Listen gehören Sasha.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import adressen
import listen_baum
import lists
from kachel_form import KachelFehler, KachelWeg, kuerzen, stueck

APP = "fokus"
RECHTE = ("lesen",)
TIEFE_GRENZE = 9
EINRUECKEN = 2                    # Zellen je Ebene
BALKEN_MAX = 10                   # Fortschritt: höchstens so viele Steine

# Katalog-Eintrag. ttl: Listen ändern sich öfter als der Kalender (abhaken
# in der TUI), eine halbe Minute reicht. Die Liste wählt man aus den
# vorhandenen (`dynamisch`: der Katalog fragt `werte` frisch).
ARTEN = {"liste": {
    "titel": "liste",
    "min": (12, 2),
    "bevorzugt": (36, 12),
    "ttl": 30,
    "felder": [
        {"name": "liste", "typ": "wahl", "titel": "liste", "dynamisch": True,
         "hilfe": "←→ blättert durch die listen"},
        {"name": "erledigte", "typ": "bool", "titel": "erledigte", "vorgabe": False,
         "hilfe": "abgehakte auch zeigen"},
        {"name": "tiefe", "typ": "zahl", "titel": "ebenen", "vorgabe": 3,
         "grenzen": {"min": 1, "max": TIEFE_GRENZE},
         "hilfe": "so tief gehen unterpunkte auf"},
    ],
}}

# Farbrollen (core/farbrollen.py): nur die Bedeutung.
R_KOPF, R_ZAHL, R_STEIN, R_FUGE = "kopf", "leise", "betont", "leise"
R_OFFEN, R_ERLEDIGT, R_FOKUS, R_ORDNER = "text", "erledigt", "betont", "text"
R_MARKE, R_MEHR, R_LEER = "leise", "mehr", "leise"

MARKE_OFFEN, MARKE_ERLEDIGT = "○ ", "✓ "
MARKE_ZU, MARKE_AUF = "▸ ", "▾ "
FOKUS = " ◆"


# ── Daten ─────────────────────────────────────────────────────────────

def _liste(lid):
    """Die Liste mit dieser id — oder KachelWeg (gelöscht, eingeordnet)."""
    for l in lists.read_lists():
        if isinstance(l, dict) and l.get("id") == lid:
            return l
    raise KachelWeg(lid)


def werte(art, name):
    """Die Listen zur Wahl (Katalog, Feld `liste`): [{wert, titel}]."""
    if art != "liste" or name != "liste":
        return []
    return [{"wert": str(l["id"]), "titel": str(l.get("name") or l["id"])}
            for l in lists.read_lists() if isinstance(l, dict) and l.get("id")]


def _pruefen(art, ref):
    if art not in ARTEN:
        raise KachelFehler("unbekannte art: %s" % art)
    if not isinstance(ref, dict) or not isinstance(ref.get("liste"), str):
        raise KachelFehler("liste fehlt")
    tiefe = ref.get("tiefe", 3)
    if isinstance(tiefe, bool) or not isinstance(tiefe, int) or not 1 <= tiefe <= TIEFE_GRENZE:
        raise KachelFehler("ebenen: 1 bis %d" % TIEFE_GRENZE)
    return ref["liste"], bool(ref.get("erledigte")), tiefe


def zeilen_baum(items, erledigte=False, tiefe=3, ebene=0):
    """Der Baum als [(eintrag, ebene, offen_aufgeklappt)] in Anzeige-Reihenfolge
    (listen_baum.ordnen je Ebene; Erledigtes nur mit `erledigte`, hinter dem
    Offenen). Unter `tiefe` Ebenen bleiben Ordner zu."""
    reihe = listen_baum.ordnen(items)
    if erledigte:
        reihe = reihe + listen_baum.ordnen(items, erledigte=True)
    raus = []
    for it in reihe:
        kids = it.get("items") if isinstance(it.get("items"), list) else []
        auf = bool(kids) and ebene + 1 < tiefe
        raus.append((it, ebene, auf))
        if auf:
            raus += zeilen_baum(kids, erledigte, tiefe, ebene + 1)
    return raus


# ── Zeichnen ──────────────────────────────────────────────────────────

def _kopf(lst, w):
    """Name links, rechts Fortschritt: Steine (wie die Bernsteinleiste der
    Ansicht) und „3/7"."""
    d, t = listen_baum.zaehlen(lst.get("items"))
    zahl = " %d/%d" % (d, t) if t else ""
    name = str(lst.get("name") or lst.get("id") or "")
    platz = w - len(zahl)
    bw = min(BALKEN_MAX, platz - min(len(name), 8) - 2) if t else 0
    if bw < 3:
        bw = 0
    name = kuerzen(name, max(0, platz - (bw + 1 if bw else 0)))
    zeile = [stueck(name, R_KOPF)]
    luecke = w - len(name) - (bw + 1 if bw else 0) - len(zahl)
    if luecke > 0:
        zeile.append(stueck(" " * luecke, R_LEER))
    if bw:
        zeile.append(stueck(" ", R_LEER))
        for s in listen_baum.steine(d, t, bw):
            zeile.append(stueck({"L": "█", "U": "░"}.get(s, " "), R_STEIN if s == "L" else R_FUGE))
    if zahl:
        zeile.append(stueck(kuerzen(zahl, w), R_ZAHL))
    return zeile


def _zeile(eintrag, w):
    """Ein Punkt als Stücke: Einrückung, Marke, Text (Ordner mit „d/t")."""
    it, ebene, auf = eintrag
    kids = it.get("items") if isinstance(it.get("items"), list) else []
    fertig = listen_baum.erledigt(it)
    if kids:
        marke = MARKE_AUF if auf else MARKE_ZU
        d, t = listen_baum.zaehlen(kids)
        rest = " %d/%d" % (d, t)
    else:
        marke, rest = (MARKE_ERLEDIGT if fertig else MARKE_OFFEN), ""
    rolle = R_ERLEDIGT if fertig else (R_FOKUS if it.get("focus") else
                                       (R_ORDNER if kids else R_OFFEN))
    text = str(it.get("text") or "") + (FOKUS if it.get("focus") else "")
    rein = " " * min(EINRUECKEN * ebene, max(0, w - 4))
    frei = max(0, w - len(rein) - len(marke))
    if len(text) + len(rest) > frei:
        rest = rest if frei - len(rest) >= 4 else ""
        text = kuerzen(text, frei - len(rest))
    zeile = [stueck(rein, R_LEER), stueck(marke, R_MARKE), stueck(text, rolle)]
    if rest:
        zeile.append(stueck(rest, R_ZAHL))
    return zeile


def _fenster(reihe, oben, platz):
    """Sichtbare Zeilen bei Versatz `oben` und `platz` Zeilen: (liste,
    versteckt_unten). Passt nicht alles, kostet „+N" eine Zeile — wie die
    Kalender-Kachel."""
    rest = reihe[oben:]
    if len(rest) <= platz:
        return rest, 0
    if platz <= 0:
        return [], len(rest)
    return rest[:platz - 1], len(rest) - (platz - 1)


def bild(lst, erledigte, tiefe, w, h, oben=0):
    """→ (zeilen, oben, oben_max) in w×h Zellen."""
    reihe = zeilen_baum(lst.get("items"), erledigte, tiefe)
    platz = h - 1
    oben_max = max(0, len(reihe) - platz)
    oben = max(0, min(int(oben or 0), oben_max))
    zeilen = [_kopf(lst, w)]
    if not reihe:
        _d, t = listen_baum.zaehlen(lst.get("items"))
        leer = "alles erledigt" if t else "noch leer"
        return zeilen + [[stueck(kuerzen(leer, w), R_LEER)]][:platz], 0, 0
    sicht, versteckt = _fenster(reihe, oben, platz)
    zeilen += [_zeile(e, w) for e in sicht]
    if versteckt:
        zeilen.append([stueck(kuerzen("+%d weitere" % versteckt, w), R_MEHR)])
    return zeilen, oben, oben_max


def _klartext(lst, reihe):
    """Rückfall für Programme ohne ZENTRALE (Obsidian): kurz, lesbar."""
    d, t = listen_baum.zaehlen(lst.get("items"))
    raus = ["%s (%d/%d)" % (lst.get("name") or lst.get("id"), d, t)]
    for it, ebene, _auf in reihe[:60]:
        raus.append("%s- [%s] %s" % ("  " * ebene, "x" if listen_baum.erledigt(it) else " ",
                                     it.get("text") or ""))
    return "\n".join(raus)[:2000]


# ── Schnittstelle für den Hub ─────────────────────────────────────────

def kachel(art, ref, w, h, oben=0):
    """Inhalt der Kachel in w×h Zellen → {zeilen, text, oben, oben_max}."""
    lid, erledigte, tiefe = _pruefen(art, ref)
    lst = _liste(lid)
    zeilen, oben, oben_max = bild(lst, erledigte, tiefe, w, h, oben)
    return {"zeilen": zeilen, "oben": oben, "oben_max": oben_max,
            "text": _klartext(lst, zeilen_baum(lst.get("items"), erledigte, tiefe))}


def bevorzugt(art, ref):
    """Bevorzugte Innengröße für GENAU diese Liste → (w, h): so hoch, dass
    alles Platz hat (höchstens 16 Zeilen), so breit wie der längste Punkt
    (24 bis 48)."""
    lid, erledigte, tiefe = _pruefen(art, ref)
    lst = _liste(lid)
    reihe = zeilen_baum(lst.get("items"), erledigte, tiefe)
    breit = max([len(str(lst.get("name") or "")) + 16] +
                [EINRUECKEN * e + 2 + len(str(it.get("text") or "")) + 6 for it, e, _a in reihe])
    return max(24, min(48, breit)), max(3, min(16, 1 + len(reihe)))


def aktion(art, ref, was):
    """„oeffnen" → die Adresse der Liste, zentrale://fokus/<liste>. Welche
    Ansicht das wird, entscheidet die Oberfläche."""
    lid, _e, _t = _pruefen(art, ref)
    if was != "oeffnen":
        raise KachelFehler("unbekannte aktion: %s" % was)
    _liste(lid)                                   # weg? → „weg", nicht ins Leere zeigen
    return {"zeige": {"adresse": adressen.bauen(APP, [lid])}}
