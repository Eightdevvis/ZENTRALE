# core/morgenblick_bild.py
#
# Der Morgenblick als HTML-Datei — deterministisch aus Python, nie von der
# KI geschrieben: die KI liefert Sätze (JSON), dieses Modul setzt sie in die
# Seite. So kann kein Wort aus einer Mail oder einem Termin zu Markup
# werden: ALLES Gesammelte und alles, was die KI schreibt, geht durch
# html.escape (2026-10-08).
#
# Gestaltung nach der Vorlage „morning" (memory/werkzeuge/morgenblick.md):
# zwei Bänder, oben das Gelände (eine Linie, Höhe = Last, Termin-Punkte
# darauf) und drei Akte, unten „Braucht dich" und „Erledigt". Fraunces 600
# nur für die Überschrift, als base64 eingebettet (SIL OFL 1.1, Lizenz in
# core/morgenblick_assets/OFL.txt). Keine Skripte, keine fremden Adressen —
# die Seite lädt nichts nach.
#
# Dienst (Schicht 2): kennt nur Termine und fertige Sätze.

import base64
import html
import math
import os

import morgenblick_daten as daten

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "morgenblick_assets")
SCHRIFT = os.path.join(_ASSETS, "fraunces-latin-600-normal.woff2")

# Farben der Vorlage
PAPIER_OBEN, PAPIER_UNTEN, KANTE = "#F9F9F7", "#FCFCFB", "#E1E1DF"
TINTE, TINTE_WEICH, TINTE_GRAU, HAARLINIE = "#2E2C27", "#6B6A63", "#B4B3A8", "#E4E3DC"
TON, TON_HOVER = "#C6613F", "#AE5133"

# Das Gelände: 840 × 170, die Akte haben ihre Mitte bei 140/420/700.
BREITE, HOEHE = 840, 170
AKT_BREITE = BREITE / 3
BASIS = 134                       # wo die Linie an einem leeren Tag liegt
BERG = 96                         # höchster Anstieg über der Basis
LAST_VOLL = 1.2                   # so viel Last = ganz oben (1 = durchgehend belegt)
WEICH = 50                        # Minuten: wie weich die Flanken sind
WELLE = 1.2                       # stilles Wasser: so klein bleibt die Welle
SCHRITT = 6                       # Abstand der Stützpunkte in px

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
              "Samstag", "Sonntag")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")

_FRIST = ("frist", "abgabe", "deadline", "einreichen", "letzter tag", "bis heute")


def e(text) -> str:
    """Escapen — für Text UND Attribute (auch Anführungszeichen)."""
    return html.escape(str(text if text is not None else ""), quote=True)


def datumszeile(d) -> str:
    """date → 'Donnerstag · 8. Oktober 2026'."""
    return f"{WOCHENTAGE[d.weekday()]} · {d.day}. {MONATE[d.month - 1]} {d.year}"


# ── Das Gelände ────────────────────────────────────────────────────────

class Gelaende:
    """Die Linie des Tages. x(t) bildet jeden Akt auf ein Drittel der
    Breite ab; y(x) ist die Höhe der Linie an dieser Stelle. Termin-Punkte
    sind Stützpunkte der Linie — sie liegen also genau darauf."""

    def __init__(self, termine, form):
        self.termine = termine
        self.form = form
        self.anfang, self.ende = daten.fenster(termine)
        self.grenzen = [(self.anfang, daten.AKT_GRENZEN[0]), daten.AKT_GRENZEN,
                        (daten.AKT_GRENZEN[1], self.ende)]

    def x(self, t) -> float:
        t = min(max(t, self.anfang), self.ende)
        for nr, (a, b) in enumerate(self.grenzen):
            if t <= b or nr == 2:
                return nr * AKT_BREITE + (t - a) / max(1, b - a) * AKT_BREITE
        return BREITE

    def t(self, x) -> float:
        nr = min(2, max(0, int(x // AKT_BREITE)))
        a, b = self.grenzen[nr]
        return a + (x - nr * AKT_BREITE) / AKT_BREITE * (b - a)

    def last(self, t) -> float:
        """Wie viel um t herum belegt ist: jeder Termin als weichgezeichnete
        Stufe (Normalverteilung, σ = WEICH). Ein kurzer Termin wird ein
        Hügel, ein langer Block oder eine dichte Folge ein Berg — so liest
        man die Last, nicht die Zahl der Termine."""
        summe = 0.0
        for tm in self.termine:
            if tm.get("start") is None:
                continue
            a, b = tm["start"], tm["start"] + daten.dauer(tm)
            summe += 0.5 * (math.erf((t - a) / (WEICH * math.sqrt(2)))
                            - math.erf((t - b) / (WEICH * math.sqrt(2))))
        return summe

    def y(self, x) -> float:
        hub = BERG * min(self.last(self.t(x)), LAST_VOLL) / LAST_VOLL
        return round(BASIS - hub + WELLE * math.sin(x / 23.0), 2)

    def punkte(self) -> list:
        """[{x, y, r, hohl, titel}] — ein Punkt je Termin mit Uhrzeit, in
        der Mitte des Termins. r 6–13 nach Dauer; hohl = echte
        Überschneidung."""
        hohl = {i for paar in daten.ueberschneidungen(self.termine) for i in paar}
        raus = []
        for i, tm in enumerate(self.termine):
            if tm.get("start") is None:
                continue
            d = daten.dauer(tm)
            x = round(self.x(tm["start"] + d / 2), 2)
            raus.append({"x": x, "y": self.y(x), "r": min(13, 6 + d // 30),
                         "hohl": i in hohl, "titel": tm.get("titel", "")})
        return raus

    def stuetzen(self) -> list:
        """Alle Stützpunkte der Linie, von 0 bis BREITE, Punkte inklusive."""
        xs = {float(x) for x in range(0, BREITE + 1, SCHRITT)} | {float(BREITE)}
        xs |= {p["x"] for p in self.punkte()}
        return [(x, self.y(x)) for x in sorted(xs)]

    def pfad(self, stuetzen=None, versatz=0.0, faktor=1.0) -> str:
        pts = stuetzen or self.stuetzen()
        teile = []
        for i, (x, y) in enumerate(pts):
            yy = BASIS - (BASIS - y) * faktor
            teile.append(f"{'M' if i == 0 else 'L'}{min(BREITE, x + versatz):.1f} {yy:.1f}")
        return " ".join(teile)

    def motive(self) -> list:
        """Höchstens ein Motiv je Akt, Ton höchstens einmal: [{art, akt, x,
        y, ton}]. Halbe Sonne = Start vor 7:30, Mond = Ende nach 21 Uhr,
        Flagge = Frist, Sonne = ein Akt ohne Termin (einmal am Tag), Vögel =
        zwei Stunden Luft in einem Akt mit Terminen (einmal am Tag)."""
        akte = daten.akte(self.termine)
        zeitig = [t for t in self.termine if t.get("start") is not None]
        raus, sonne, voegel = {}, False, False

        def hoch(nr):
            a = int(nr * AKT_BREITE)
            return min(self.y(x) for x in range(a, a + int(AKT_BREITE), SCHRITT))

        def setzen(nr, art, x=None):
            if nr not in raus:
                raus[nr] = {"art": art, "akt": nr,
                            "x": x if x is not None else nr * AKT_BREITE + AKT_BREITE / 2,
                            "y": max(22, hoch(nr) - 34), "ton": False}

        for t in zeitig:                      # Fristen zuerst: sie sind Daten
            if any(w in t.get("titel", "").lower() for w in _FRIST):
                nr = next(n for n, a in enumerate(akte) if self.termine.index(t) in a["termine"])
                setzen(nr, "flagge", self.x(t["start"] + daten.dauer(t) / 2))
        if zeitig and min(t["start"] for t in zeitig) < 7 * 60 + 30:
            setzen(0, "halbsonne")
        if zeitig and max(t["start"] + daten.dauer(t) for t in zeitig) > 21 * 60:
            setzen(2, "mond")
        for nr in (1, 0, 2):                  # die Mitte des Tages zuerst
            if not akte[nr]["termine"] and not sonne and nr not in raus:
                setzen(nr, "sonne")
                sonne = True
        for nr, a in enumerate(akte):
            if voegel or nr in raus or not a["termine"]:
                continue
            if self._luft(a) >= 120:
                setzen(nr, "voegel")
                voegel = True
        liste = [raus[n] for n in sorted(raus)]
        for art in ("flagge", "sonne"):       # der eine Ton-Akzent
            m = next((m for m in liste if m["art"] == art), None)
            if m:
                m["ton"] = True
                break
        return liste

    def _luft(self, akt) -> int:
        """Längste freie Spanne im Fenster eines Akts, in Minuten."""
        a, b = akt["fenster"]
        belegt = sorted((self.termine[i]["start"],
                         self.termine[i]["start"] + daten.dauer(self.termine[i]))
                        for i in akt["termine"])
        luft, ab = 0, a
        for s, en in belegt:
            luft = max(luft, s - ab)
            ab = max(ab, en)
        return max(luft, b - ab)


def _motiv_svg(m) -> str:
    x, y = m["x"], m["y"]
    farbe = TON if m["ton"] else TINTE_GRAU
    art = m["art"]
    if art == "sonne":
        strahlen = " ".join(
            f'<line x1="{x + 13 * math.cos(w):.1f}" y1="{y + 13 * math.sin(w):.1f}" '
            f'x2="{x + 18 * math.cos(w):.1f}" y2="{y + 18 * math.sin(w):.1f}"/>'
            for w in (k * math.pi / 4 for k in range(8)))
        return (f'<g class="motiv sonne" stroke="{farbe}" stroke-width="1.6" fill="none" '
                f'stroke-linecap="round"><circle cx="{x:.1f}" cy="{y:.1f}" r="8"/>{strahlen}</g>')
    if art == "halbsonne":
        return (f'<g class="motiv halbsonne" stroke="{farbe}" stroke-width="1.6" fill="none" '
                f'stroke-linecap="round"><path d="M{x - 10:.1f} {y:.1f} A10 10 0 0 1 {x + 10:.1f} {y:.1f}"/>'
                f'<line x1="{x - 16:.1f}" y1="{y:.1f}" x2="{x + 16:.1f}" y2="{y:.1f}"/>'
                f'<line x1="{x:.1f}" y1="{y - 14:.1f}" x2="{x:.1f}" y2="{y - 18:.1f}"/></g>')
    if art == "mond":
        return (f'<path class="motiv mond" fill="none" stroke="{farbe}" stroke-width="1.6" '
                f'd="M{x + 3:.1f} {y - 10:.1f} A10 10 0 1 0 {x + 3:.1f} {y + 10:.1f} '
                f'A7.5 7.5 0 1 1 {x + 3:.1f} {y - 10:.1f} Z"/>')
    if art == "flagge":
        return (f'<g class="motiv flagge" stroke="{farbe}" stroke-width="1.6" fill="none" '
                f'stroke-linejoin="round"><line x1="{x:.1f}" y1="{y + 14:.1f}" x2="{x:.1f}" '
                f'y2="{y - 10:.1f}"/><path d="M{x:.1f} {y - 10:.1f} L{x + 12:.1f} {y - 6:.1f} '
                f'L{x:.1f} {y - 2:.1f}" fill="{farbe}"/></g>')
    # voegel: zwei kleine Bögen
    def vogel(vx, vy, s):
        return (f'<path d="M{vx - 6 * s:.1f} {vy:.1f} Q{vx - 3 * s:.1f} {vy - 4 * s:.1f} '
                f'{vx:.1f} {vy:.1f} Q{vx + 3 * s:.1f} {vy - 4 * s:.1f} {vx + 6 * s:.1f} {vy:.1f}"/>')
    return (f'<g class="motiv voegel" stroke="{farbe}" stroke-width="1.4" fill="none" '
            f'stroke-linecap="round">{vogel(x - 8, y, 1)}{vogel(x + 9, y - 7, 0.8)}</g>')


def gelaende_svg(termine, form) -> str:
    g = Gelaende(termine, form)
    stuetzen = g.stuetzen()
    teile = [f'<svg class="gelaende" viewBox="0 0 {BREITE} {HOEHE}" role="img" '
             f'aria-label="Der Tag als Linie: je höher, desto mehr steht an" '
             f'xmlns="http://www.w3.org/2000/svg">']
    if form == "HEAVY":                       # zweiter Grat: Tiefe
        teile.append(f'<path class="grat2" d="{g.pfad(stuetzen, versatz=26, faktor=0.6)}" '
                     f'fill="none" stroke="{HAARLINIE}" stroke-width="1.6" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
    teile.append(f'<path class="linie" d="{g.pfad(stuetzen)}" fill="none" stroke="{TINTE}" '
                 f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    for m in g.motive():
        teile.append(_motiv_svg(m))
    for p in g.punkte():
        if p["hohl"]:
            teile.append(f'<circle class="punkt hohl" cx="{p["x"]}" cy="{p["y"]}" r="{p["r"]}" '
                         f'fill="{PAPIER_OBEN}" stroke="{TINTE}" stroke-width="2">'
                         f'<title>{e(p["titel"])}</title></circle>')
        else:
            teile.append(f'<circle class="punkt" cx="{p["x"]}" cy="{p["y"]}" r="{p["r"]}" '
                         f'fill="{TINTE}"><title>{e(p["titel"])}</title></circle>')
    teile.append("</svg>")
    return "".join(teile)


# ── Die Seite ──────────────────────────────────────────────────────────

def _schrift_css() -> str:
    try:
        with open(SCHRIFT, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""                             # dann eben Georgia
    return ('@font-face{font-family:"Fraunces";font-style:normal;font-weight:600;'
            f'font-display:block;src:url(data:font/woff2;base64,{b64}) format("woff2")}}')


_CSS = f"""
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0}}
body{{background:{PAPIER_UNTEN};color:{TINTE};overflow-wrap:break-word;font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}}
.band{{width:100%}}
.oben{{background:{PAPIER_OBEN};border-bottom:1px solid {KANTE}}}
.unten{{background:{PAPIER_UNTEN}}}
.innen{{max-width:860px;margin:0 auto;padding:44px 24px 36px}}
.unten .innen{{padding-top:36px;padding-bottom:56px}}
.datum{{margin:0 0 10px;font-size:13px;color:{TINTE_WEICH};letter-spacing:.01em}}
h1{{margin:0 0 26px;font-family:"Fraunces",Georgia,serif;font-weight:600;font-style:normal;font-size:40px;line-height:1.15;letter-spacing:-.01em;max-width:24em}}
.gelaende{{display:block;width:100%;height:auto;overflow:visible}}
.akte{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:6px}}
.akt b{{display:block;font-size:14px;font-weight:600;margin-bottom:2px}}
.akt p{{margin:0;font-size:14px;color:{TINTE_WEICH}}}
h2{{margin:0 0 6px;font-size:13px;font-weight:600;color:{TINTE_WEICH}}}
.liste{{list-style:none;margin:0 0 34px;padding:0}}
.liste li{{display:grid;grid-template-columns:30px 1fr;padding:14px 0;border-top:1px solid {HAARLINIE}}}
.liste li:last-child{{border-bottom:1px solid {HAARLINIE}}}
.nr{{color:{TINTE_GRAU};font-variant-numeric:tabular-nums;font-size:14px;padding-top:1px}}
.liste b{{display:block;font-size:15px;font-weight:600}}
.liste p{{margin:3px 0 0;font-size:14px;color:{TINTE_WEICH}}}
.knopf{{display:inline-block;margin-top:10px;background:{TON};color:#fff;border-radius:8px;padding:9px 16px;font-size:13px;font-weight:500;line-height:1.2;text-decoration:none}}
.knopf:hover{{background:{TON_HOVER}}}
.ruhig{{margin:0;font-size:15px;color:{TINTE_WEICH}}}
@media (max-width:640px){{
 .innen{{padding:30px 16px 26px}}
 h1{{font-size:30px}}
 .akte{{grid-template-columns:1fr;gap:14px}}
}}
"""


def _akte_html(akte_saetze, akte) -> str:
    teile = []
    for a, satz in zip(akte, akte_saetze):
        spanne = f'{daten.uhr(a["von"])} – {daten.uhr(a["bis"])}'
        teile.append(f'<div class="akt"><b>{e(spanne)}</b><p>{e(satz)}</p></div>')
    return '<div class="akte">' + "".join(teile) + "</div>"


def _liste_html(ueberschrift, eintraege) -> str:
    if not eintraege:
        return ""
    zeilen = []
    for nr, it in enumerate(eintraege, 1):
        knopf = ""
        k = it.get("knopf")
        if k and k.get("href"):
            knopf = f'<a class="knopf" href="{e(k["href"])}">{e(k.get("beschriftung"))}</a>'
        zeilen.append(f'<li><span class="nr">{nr}</span><div><b>{e(it.get("titel"))}</b>'
                      f'<p>{e(it.get("satz"))}</p>{knopf}</div></li>')
    return f'<h2>{e(ueberschrift)}</h2><ol class="liste">' + "".join(zeilen) + "</ol>"


def seite(blick: dict, termine: list, form: str, tag) -> str:
    """Die ganze Seite. blick: {ueberschrift, akte: [3 Sätze], braucht_dich,
    erledigt: [{titel, satz, knopf?}]} — geprüft von morgenblick.py."""
    akte = daten.akte(termine)
    saetze = (list(blick.get("akte") or []) + ["", "", ""])[:3]
    braucht = blick.get("braucht_dich") or []
    erledigt = blick.get("erledigt") or []
    unten = (_liste_html("Braucht dich", braucht) + _liste_html("Erledigt", erledigt)) \
        or '<p class="ruhig">Heute Morgen braucht dich nichts.</p>'
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Morgenblick · {e(datumszeile(tag))}</title>'
        f'<style>{_schrift_css()}{_CSS}</style></head><body>'
        f'<section class="band oben"><div class="innen">'
        f'<p class="datum">{e(datumszeile(tag))}</p>'
        f'<h1>{e(blick.get("ueberschrift"))}</h1>'
        f'{gelaende_svg(termine, form)}{_akte_html(saetze, akte)}'
        f'</div></section>'
        f'<section class="band unten"><div class="innen">{unten}</div></section>'
        '</body></html>')
