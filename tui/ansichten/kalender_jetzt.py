"""Kalender-TUI: die Jetzt-Linie (seit 20.10.2026) — reine Funktionen.

Sasha: „füge einen goldenen kleinen strich mit kleinem pfeil links dran
hinzu, der genau anzeigt, wo die zeit grade runterläuft, in der
wochenansicht". 21.10.: „ja der soll immer drüber laufen, immer sichtbar
sein, klaro."

  C (Woche)  in der Spalte von HEUTE, zur aktuellen Uhrzeit (auf die
             nächstliegende Rasterzeile gerundet): „►" im Spalt links der
             Tagesspalte, dann „─" über die GANZE Spalte, durchgehend golden
             — auch über Terminen, Glas, Phasen und Deadlines. Freie Zellen
             bekommen den Strich; Zellen mit Text (Blocktitel, Zeitzeile)
             behalten ihr Zeichen, nur die Schrift wird golden (Rolle
             MARKE + darunter: Gold auf dem Grund der Zelle, kalender.py
             wählt die Goldstufe mit ≥ 3:1). Deadlines: ⚑ und Text bleiben
             rot, nur ihr „━" wird golden — der goldene ► links steht immer.
             Nur, wenn heute in der Woche liegt und die Uhrzeit im Fenster.
  A (Liste)  ein „►" vor dem Termin von heute, der gerade läuft, sonst vor
             dem nächsten.

Gold (farben.KAL „jetzt"), dünn — gegen die Deadline (rot, „━" dick, ⚑)
nicht zu verwechseln. Gerechnet wird bei jedem Zeichnen mit der Uhr
(core/uhr.py); die TUI zeichnet mindestens alle 250 ms neu, die Linie
wandert also von selbst.
"""
from __future__ import annotations

from .basis import kern_pfad

kern_pfad()
import uhr  # noqa: E402  – core/uhr.py: die eine Uhr

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

# ── Regler (Sasha entscheidet die Optik) ───────────────────────────────
ROLLE = "k_jetzt"
PFEIL = "►"
STRICH = "─"
C_ZEIGEN = True
A_ZEIGEN = True
# „^<darunter>": goldene Schrift auf dem Grund der Rolle darunter (Block,
# Glas, Stylebox, Deadline-Linie) — kalender.py löst sie auf.
MARKE = "^"
KONTRAST_MIN = 3.0
# Goldstufen hell → dunkel (bis 95,95,0 die xterm-256-Töne, dann Schwarz-
# Gold). Reicht die Theme-Farbe auf einem Grund nicht (Gold auf hellem
# Pastell tags, auf Neon nachts), nimmt kalender.py die nächste Stufe mit
# ≥ KONTRAST_MIN — gemessen an der Farbe, die das Terminal wirklich zeigt.
GOLDSTUFEN = ((255, 255, 175), (255, 255, 135), (255, 215, 95), (255, 215, 0),
              (215, 175, 0), (175, 135, 0), (135, 95, 0), (95, 95, 0),
              (75, 55, 0), (48, 38, 0))
GLAS = "~"          # wie kalender_ansichten.GLAS (Kreis-Import vermeiden)
DL_ROLLE = "k_dl"   # kalender_deadline.ROLLEN
DL_LINIE = "━╍"     # kalender_deadline.LINIE, LINIE_UNV


def jetzt():
    return uhr.jetzt()


def minute(dt) -> int:
    return dt.hour * 60 + dt.minute


def c_zeile(jm: int, lo: int, m: int, n: int) -> int | None:
    """Zeile (0…n-1) der Minute jm im Fenster lo…lo+n*m, auf die
    nächstliegende Rasterzeile gerundet; außerhalb None."""
    if n < 1 or m < 1 or not lo <= jm < lo + n * m:
        return None
    return min(n - 1, (2 * (jm - lo) + m) // (2 * m))


def _frei(ch: str, rolle: str) -> bool:
    """Darf der Strich hier hin? Leer, Punktlinie, Phasen-Muster."""
    return (rolle == "dim" and ch == " ") or (rolle == "faint" and ch in " ·") \
        or rolle.startswith("k_m_")


def c_zeichnen(lw, y0: int, n: int, lo: int, m: int, woche: list, x0: int,
               colw: int, dt=None) -> int | None:
    """Die Jetzt-Linie in die Woche (Spalte i beginnt bei x0 + i*colw, ist
    colw-1 breit; der Spalt davor trägt den Pfeil). -> die Zeile oder None."""
    if not C_ZEIGEN:
        return None
    dt = dt or jetzt()
    if dt.date() not in woche:
        return None
    k = c_zeile(minute(dt), lo, m, n)
    if k is None:
        return None
    y = y0 + k
    if not 0 <= y < lw.h:
        return None
    x = x0 + woche.index(dt.date()) * colw
    reihe = lw.z[y]
    for cx in range(max(0, x), min(lw.b, x + colw - 1)):
        reihe[cx] = zelle(*reihe[cx])
    if 0 <= x - 1 < lw.b:
        reihe[x - 1] = (PFEIL, ROLLE)
    return y


def zelle(ch: str, r: str) -> tuple:
    """Eine Zelle der Jetzt-Zeile: Freies → goldener Strich (auf dem Grund
    der Theme-Farbe); auf einer Fläche/Glas der Strich bzw. das Zeichen in
    Gold auf deren Grund; Deadline: nur die Linie golden, ⚑ und Text rot."""
    teile = r.split(GLAS)
    if r.startswith(DL_ROLLE):
        return (ch, MARKE + r) if ch in DL_LINIE else (ch, r)
    if len(teile) == 1 and _frei(ch, r):
        return STRICH, ROLLE
    if ch == " " or (len(teile) == 2 and _frei(ch, teile[0])):
        return STRICH, MARKE + r
    return ch, MARKE + r


def gold(grund, gold0=None, rund=None) -> tuple:
    """Goldstufe für Schrift auf `grund` (RGB): die Theme-Farbe `gold0`,
    wenn sie ≥ KONTRAST_MIN hat — sonst die nächstliegende Stufe in
    GOLDSTUFEN, die es schafft (zum Dunklen hin auf hellem Grund, zum
    Hellen auf dunklem). Schafft es keine: die mit dem besten Kontrast.
    `rund`: RGB → was das Terminal daraus macht (256er-Modus), daran wird
    gemessen; zurück kommt die gerundete Farbe."""
    rund = rund or tuple
    k = pixel.kontrast
    if gold0 is not None and k(rund(gold0), grund) >= KONTRAST_MIN:
        return rund(gold0)
    stufen = [rund(g) for g in GOLDSTUFEN]
    start = (min(range(len(GOLDSTUFEN)), key=lambda i: pixel._d2(GOLDSTUFEN[i], gold0))
             if gold0 is not None else 3)
    dunkler = sum(grund) > sum(GOLDSTUFEN[start])      # heller Grund → dunkleres Gold
    nach = sorted(range(len(stufen)),
                  key=lambda i: (abs(i - start), (i < start) if dunkler else (i > start)))
    for i in nach:
        if k(stufen[i], grund) >= KONTRAST_MIN:
            return stufen[i]
    return max(stufen, key=lambda g: k(g, grund))


def a_ziel(eintraege: list, dt) -> object | None:
    """A: der Termin von heute, der gerade läuft — sonst der nächste. Nur
    mit Uhrzeit, ohne Ausgefallenes; Ganztägiges zählt nicht."""
    if not A_ZEIGEN:
        return None
    jm = minute(dt)
    laufend = naechst = None
    for t in eintraege:
        s, e = t.get("start"), t.get("ende")
        if s is None or t.get("aus") or t.get("deadline"):
            continue
        if s <= jm < (e if e is not None and e > s else s + 1):
            laufend = laufend or t
        elif s >= jm and (naechst is None or s < naechst["start"]):
            naechst = t
    return laufend or naechst
