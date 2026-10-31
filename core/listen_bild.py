# core/listen_bild.py
#
# DAS Bild einer Liste — die eine Stelle, an der beschrieben ist, wie ein
# Listeneintrag aussieht. Sasha 2026-10-11: „Programm und Kachel müssen
# IMMER synchron sein … Kacheln werden nie per Hand nachgeschrieben." Die
# Vollansicht (tui/ansichten/fokus.py) und die Listen-Kachel
# (core/kachel_fokus.py) zeichnen beide NUR das, was hier herauskommt; ändert
# sich das Design hier, formt sich die Kachel von selbst mit.
#
# Ausgabe: neutrale Zeilen aus Stücken [text, rolle] — dasselbe Format wie
# eine Kachel-Antwort (core/kachel_form.py, memory/hub/hub_bauplan.md
# „Kacheln"); die Rollen stammen aus dem Wörterbuch core/farbrollen.py (ein
# Test prüft das, importiert wird es hier bewusst nicht). Kein curses, keine
# Farbe: jede Oberfläche bildet die Rollen auf ihre Farben ab.
#
# Aufbau einer Ebene (ebene()):
#   Kopf        Pfad der Ebene („einkauf / baumarkt"), Rolle kopf
#   Bernstein   2 Zeilen ▐███ ░░░▌ 3/7 — Status der Ebene, ein Stein je
#               Punkt; fehlt, wenn die Ebene nichts zählt
#   Trennlinie  ────
#   Kästen      je Eintrag 3 Zeilen ┌─┐ │ ▸ titel ◆ │ └─┘, nur der Titel
#               mit Markern (▸ Ordner, ★ Projekt, ◆ Fokus); gewählt: Rahmen
#               betont, Titel in Rolle „auswahl"; passt nicht alles, trägt der
#               letzte Kasten unten „+N"
# Dazu Lage-Angaben (welche Zeile der Bernstein ist, welche Zeile zu welchem
# Kasten gehört), damit eine Oberfläche veredeln kann (die TUI malt den
# Bernstein als Pixel-Steine) — WAS WO steht, bestimmt aber nur dieses Modul.
#
# Teil des Listenprogramms (lists.py, listen_baum.py, listen_bild.py,
# kachel_fokus.py — beim Auszug ein Paket, memory/hub/listen_app.md).
# Stdlib-only und nur listen_baum als Import: die TUI läuft auch auf einem
# Aussenposten ohne Backend (deploy/aussenposten.txt).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import listen_baum

# Rollen (Namen aus core/farbrollen.py — nur die Bedeutung)
R_KOPF = "kopf"
R_RAHMEN, R_RAHMEN_GEWAEHLT = "leise", "betont"
R_TITEL, R_GEWAEHLT = "betont", "auswahl"
R_STEIN, R_FASSUNG, R_ZAEHLER = "betont", "leise", "betont"
R_TRENN, R_LEER, R_MEHR = "leise", "leise", "mehr"
ROLLEN = (R_KOPF, R_RAHMEN, R_RAHMEN_GEWAEHLT, R_TITEL, R_GEWAEHLT, R_STEIN,
          R_FASSUNG, R_ZAEHLER, R_TRENN, R_LEER, R_MEHR)

KASTEN_HOEHE = 3
BERNSTEIN_HOEHE = 2
MARKE_ORDNER, MARKE_PROJEKT, MARKE_FOKUS = "▸ ", " ★", " ◆"
ABGESCHLOSSEN = " · abgeschlossen"
LEER_TEXT = {"abgeschlossen": "noch nichts abgeschlossen",
             "erledigt": "alles erledigt ◆",
             "leer": "noch leer"}


def _kuerzen(text, breite):
    """Auf `breite` Zeichen, „…" am Ende, wenn etwas fehlt (wie
    kachel_form.kuerzen — hier eigen, weil die TUI ohne Kern auskommt)."""
    text = "".join(c if c.isprintable() else " " for c in str(text))
    if breite <= 0:
        return ""
    if len(text) <= breite:
        return text
    return text[:breite - 1] + "…" if breite > 1 else text[:1]


# ── Ein Eintrag ───────────────────────────────────────────────────────

def eintrag(roh, projekt_marke=True):
    """Ein Listen-Dict oder Eintrag → was sein Kasten zeigt: {titel, ordner,
    fokus, projekt}. projekt_marke=False lässt den ★ weg (in der Wurzel der
    Vollansicht steht die Zone „projekte" schon dafür)."""
    roh = roh if isinstance(roh, dict) else {}
    kids = roh.get("items")
    return {"titel": str(roh.get("text") or roh.get("name") or ""),
            "ordner": isinstance(kids, list) and bool(kids),
            "fokus": bool(roh.get("focus")),
            "projekt": bool(projekt_marke and roh.get("project"))}


def titel(e):
    """Der Text im Kasten: ▸ vor Ordnern, ★ hinter Projekten, ◆ hinter dem Fokus."""
    t = (MARKE_ORDNER if e.get("ordner") else "") + str(e.get("titel") or "")
    if e.get("projekt"):
        t += MARKE_PROJEKT
    if e.get("fokus"):
        t += MARKE_FOKUS
    return t


def kasten(e, w, gewaehlt=False, mehr=0):
    """EIN Eintrag als Kasten: 3 Zeilen, genau w Zellen breit. mehr > 0
    schreibt „+N" in den unteren Rand (so viele folgen noch)."""
    rand = R_RAHMEN_GEWAEHLT if gewaehlt else R_RAHMEN
    t = titel(e)
    if w < 5:                                   # kein Platz für Rahmen
        return [[], [[_kuerzen(t, w), R_GEWAEHLT if gewaehlt else R_TITEL]], []]
    innen = w - 2
    t = _kuerzen(t, innen - 2)
    mitte = [["│ ", rand], [t, R_GEWAEHLT if gewaehlt else R_TITEL],
             [" " * (innen - 1 - len(t)) + "│", rand]]
    schild = " +%d " % mehr if mehr > 0 else ""
    if schild and len(schild) + 2 <= innen:
        unten = [["└" + "─" * (innen - len(schild) - 1), rand], [schild, R_MEHR],
                 ["─┘", rand]]
    else:
        unten = [["└" + "─" * innen + "┘", rand]]
    return [[["┌" + "─" * innen + "┐", rand]], mitte, unten]


# ── Status der Ebene ──────────────────────────────────────────────────

def bernstein(done, total, w, gewaehlt=False):
    """Die Bernsteinleiste: (2 Zeilen, Breite der Leiste mit Fassung) oder
    ([], 0), wenn nichts zählt. Ein Stein je Punkt (listen_baum.steine),
    rechts der Zähler „ d/t" — gewählt in Rolle „auswahl"."""
    if not total or total <= 0 or w < 3:
        return [], 0
    zahl = " %d/%d" % (done, total)
    if w - 2 - len(zahl) < 1:
        zahl = ""
    sw = max(1, w - 2 - len(zahl))
    reihe = [["▐", R_FASSUNG]]
    for c in listen_baum.steine(done, total, sw):
        zeichen, rolle = {"L": ("█", R_STEIN), "U": ("░", R_FASSUNG)}.get(c, (" ", R_FASSUNG))
        letztes = reihe[-1]
        if len(reihe) > 1 and letztes[1] == rolle and letztes[0][-1] == zeichen:
            letztes[0] += zeichen                   # gleiche Zeichen: ein Stück
        else:
            reihe.append([zeichen, rolle])
    reihe.append(["▌", R_FASSUNG])
    oben = [list(s) for s in reihe]
    if zahl:
        oben.append([zahl, R_GEWAEHLT if gewaehlt else R_ZAEHLER])
    return [oben, [list(s) for s in reihe]], sw + 2


def kopf(pfad, w, zusatz="", frei=0):
    """Kopfzeile: der Pfad der Ebene („liste / ordner / …")."""
    text = " / ".join(str(p) for p in (pfad or ())) + zusatz
    return [[_kuerzen(text, max(0, w - frei)), R_KOPF]]


def fenster(anzahl, platz, auswahl=None, oben=None):
    """Welche Kästen passen: (start, wie_viele, start_max). `platz` in
    Zeilen. Mit `oben` blättert man selbst (Kachel), sonst folgt das Fenster
    der `auswahl` (Vollansicht: der Cursor bleibt sichtbar)."""
    passt = max(0, platz // KASTEN_HOEHE)
    start_max = max(0, anzahl - passt)
    if oben is not None:
        start = int(oben or 0)
    elif auswahl is not None and anzahl > passt:
        start = auswahl - passt + 1
    else:
        start = 0
    start = max(0, min(start, start_max))
    return start, min(passt, anzahl - start), start_max


# ── Eine Ebene ────────────────────────────────────────────────────────

def ebene(items, w, h, pfad=(), nur_erledigte=False, auswahl=None, oben=None,
          kopf_frei=0):
    """Eine Ebene einer Liste in w×h Zellen.

    items: die direkten Einträge der Ebene; pfad: Namen bis hierher (Kopf);
    nur_erledigte: die abgeschlossenen statt der offenen zeigen (wie enter
    auf den Bernstein); auswahl: Index des gewählten Eintrags (-1 = der
    Bernstein, None = nichts gewählt); oben: erster gezeigter Eintrag
    (blättern, sonst folgt das Fenster der Auswahl); kopf_frei: so viele
    Zellen rechts im Kopf frei lassen.

    → {zeilen, bernstein: {zeile, breite, done, total, steine} | None,
       kaesten: [(zeile, index)], leer: {zeile, art} | None,
       oben, oben_max, versteckt}"""
    done, total = listen_baum.zaehlen(items)
    reihe = listen_baum.ordnen(items, nur_erledigte)
    zeilen = [kopf(pfad, w, ABGESCHLOSSEN if nur_erledigte else "", kopf_frei)]
    raus = {"zeilen": zeilen, "bernstein": None, "kaesten": [], "leer": None,
            "oben": 0, "oben_max": 0, "versteckt": 0}
    leiste, breite = bernstein(done, total, w, gewaehlt=(auswahl == -1))
    if leiste:
        # steine: the columns of the bar (listen_baum.steine) — a surface
        # that paints the bar its own way (TUI) takes them from here.
        raus["bernstein"] = {"zeile": len(zeilen), "breite": breite,
                             "done": done, "total": total,
                             "steine": "".join(listen_baum.steine(done, total, breite - 2))}
        zeilen += leiste
    zeilen.append([["─" * w, R_TRENN]])
    platz = h - len(zeilen)
    if not reihe:
        art = "abgeschlossen" if nur_erledigte else ("erledigt" if total else "leer")
        raus["leer"] = {"zeile": len(zeilen), "art": art}
        zeilen.append([[_kuerzen(LEER_TEXT[art], w), R_LEER]])
    else:
        start, n, start_max = fenster(len(reihe), platz, auswahl, oben)
        rest = len(reihe) - start - n
        for i in range(start, start + n):
            raus["kaesten"].append((len(zeilen), i))
            zeilen += kasten(eintrag(reihe[i]), w, gewaehlt=(i == auswahl),
                             mehr=rest if i == start + n - 1 else 0)
        if not n and platz > 0:
            zeilen.append([[_kuerzen("+%d" % rest, w), R_MEHR]])
        raus.update(oben=start, oben_max=start_max, versteckt=rest)
    raus["zeilen"] = zeilen[:max(0, h)]
    return raus


def bevorzugt(items, pfad=(), nur_erledigte=False):
    """Größe, in der die ganze Ebene Platz hat → (w, h) (nicht gekappt)."""
    reihe = listen_baum.ordnen(items, nur_erledigte)
    _d, total = listen_baum.zaehlen(items)
    w = max([len(" / ".join(str(p) for p in pfad)) + 2] +
            [len(titel(eintrag(it))) + 4 for it in reihe])
    h = 1 + (BERNSTEIN_HOEHE if total else 0) + 1 + max(1, KASTEN_HOEHE * len(reihe))
    return w, h


def klartext(pfad, items, nur_erledigte=False):
    """Dieselbe Ebene als kurzer Text (Rückfall für Programme ohne
    Oberfläche, z. B. Obsidian liest die Canvas-Datei)."""
    done, total = listen_baum.zaehlen(items)
    raus = ["%s (%d/%d)" % (" / ".join(str(p) for p in pfad), done, total)]
    for it in listen_baum.ordnen(items, nur_erledigte)[:60]:
        raus.append("- [%s] %s" % ("x" if listen_baum.erledigt(it) else " ", titel(eintrag(it))))
    return "\n".join(raus)[:2000]
