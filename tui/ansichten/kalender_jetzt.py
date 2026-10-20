"""Kalender-TUI: die Jetzt-Linie (seit 20.10.2026) — reine Funktionen.

Sasha: „füge einen goldenen kleinen strich mit kleinem pfeil links dran
hinzu, der genau anzeigt, wo die zeit grade runterläuft, in der
wochenansicht".

  C (Woche)  in der Spalte von HEUTE, zur aktuellen Uhrzeit (auf die
             nächstliegende Rasterzeile gerundet): „▸" im Spalt links der
             Tagesspalte, dann ein dünner Strich „─" über die Spalte. Er
             übermalt nur, was frei ist (Leerzellen, Punktlinie, Phasen-
             Muster, Glas über Freiem) golden; im Leerraum eines Termins
             läuft er in dessen Schrift weiter (DURCH_BLOCK) — Text und
             Deadlines bleiben, wie sie sind. Nur, wenn heute in der Woche liegt und
             die Uhrzeit im sichtbaren Fenster.
  A (Liste)  ein „▸" vor dem Termin von heute, der gerade läuft, sonst vor
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

# ── Regler (Sasha entscheidet die Optik) ───────────────────────────────
ROLLE = "k_jetzt"
PFEIL = "▸"
STRICH = "─"
C_ZEIGEN = True
A_ZEIGEN = True
# Über einem Termin: der Leerraum der Fläche bekommt den Strich in der
# Schrift des Blocks (Text bleibt). False: dort bleibt nur der Pfeil.
DURCH_BLOCK = True
GLAS = "~"          # wie kalender_ansichten.GLAS (Kreis-Import vermeiden)


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


def _flaeche(rolle: str) -> bool:
    """Fläche eines Termins (Kursfarbe, leise Zeitzeile, Stylebox)."""
    return rolle.endswith(("_inv", "_inv_leise")) or rolle.startswith("$")


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
        ch, r = reihe[cx]
        teile = r.split(GLAS)
        if len(teile) == 1 and _frei(ch, r):
            reihe[cx] = (STRICH, ROLLE)
        elif len(teile) == 2 and _frei(ch, teile[0]):      # Glas ohne eigene Schrift
            reihe[cx] = (STRICH, ROLLE + GLAS + teile[1])
        elif DURCH_BLOCK and len(teile) == 1 and ch == " " and _flaeche(r):
            reihe[cx] = (STRICH, r)        # Leerraum im Block: Strich in Blockschrift
    if 0 <= x - 1 < lw.b:
        reihe[x - 1] = (PFEIL, ROLLE)
    return y


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
