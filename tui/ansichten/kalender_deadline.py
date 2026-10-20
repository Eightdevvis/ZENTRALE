"""Kalender-TUI: Deadlines zeichnen (seit 20.10.2026) — reine Funktionen.

Sasha: „füg noch einen eigenen typen ‚deadline' hinzu … die deadline soll
rot leuchten in einem zeitfenster was man selbst vorher einstellen kann, je
näher man ihr kommt. sie soll auch nich oben stehen wie die ganztagsevents,
sondern halt mit ner uhrzeit, nur nen textoverlap machen und so ne deadline
hingemalt halt."

Eine Deadline ist ein Zeitpunkt (Kern: core/kalender_deadline.py; die API
liefert `typ: "deadline"` und `vorwarnung` in Minuten). Hier steht nur, wie
sie AUSSIEHT — in allen drei Ansichten gleich:

  C (Woche)  eine waagrechte Linie über die Tagesspalte zur Uhrzeit,
             „⚑ 23:59 Analysis HÜ ━━━━", über allem (nur diese eine Zeile
             wird überschrieben, nimmt keine Bahn ein); außerhalb des
             Fensters am Rand mit ▲/▼ statt ⚑.
  A (Liste)  eine Zeile „⚑ 23:59 Analysis HÜ · in 2 T".
  B (Monat)  eine Zeile „⚑23:59 Analysis HÜ".

Das Leuchten (Regler unten): außerhalb der Vorwarnung gedämpftes Rot
(Stufe 0); im Fenster je nach verbrauchtem Anteil Stufe 1, 2, 3 (Neon-Rot,
ab FLAECHE_AB als Fläche); überschritten grau (STUFE_VORBEI). Gerechnet wird
bei jedem Zeichnen mit der echten Uhr (core/uhr.py) — die TUI zeichnet
ohnehin periodisch neu, so wird es im Lauf der Zeit von selbst kräftiger.
Farben: tui/ansichten/farben.py, KAL dl0…dl3, dlx.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .basis import kern_pfad

kern_pfad()
import uhr  # noqa: E402  – core/uhr.py: die eine Uhr

TYP = "deadline"
# ── Regler (Sasha entscheidet die Optik) ───────────────────────────────
VORWARNUNG_STANDARD = 3 * 24 * 60      # wie core/kalender_deadline.py, falls die API keine liefert
# Anteil der Vorwarnung, der verbraucht sein muss, für Stufe 2 bzw. 3 (Neon).
# Mit 3 Tagen: die ersten 24 h Stufe 1, dann 2, die letzten 24 h Neon.
STUFEN_AB = (1 / 3, 2 / 3)
FLAECHE_AB = 3                         # ab dieser Stufe leuchtet der Text als Fläche
STUFE_VORBEI = -1
VORBEI_ZEIGEN = True                   # False: überschrittene Deadlines gar nicht zeigen
ZEICHEN = "⚑"
LINIE = "━"
LINIE_UNV = "╍"                        # uncommitted: leise, gestrichelt
LINIE_MIN = 3                          # so viel Linie bleibt immer (der Titel wird gekürzt)
ROLLEN = {0: "k_dl0", 1: "k_dl1", 2: "k_dl2", 3: "k_dl3", STUFE_VORBEI: "k_dlx"}


def ist(t) -> bool:
    """Ein API-Eintrag oder ein normierter Eintrag der Ansichten."""
    if not isinstance(t, dict):
        return False
    return bool(t.get("deadline")) or t.get("typ") == TYP


def vorwarnung(roh) -> int:
    v = (roh or {}).get("vorwarnung")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else VORWARNUNG_STANDARD


def _zeitpunkt(roh, tag) -> datetime | None:
    try:
        d = tag if isinstance(tag, date) else date.fromisoformat(tag)
        h, m = str(roh.get("time") or "").split(":")
        return datetime.combine(d, datetime.min.time()) + timedelta(hours=int(h), minutes=int(m))
    except (TypeError, ValueError, AttributeError):
        return None


def rest_minuten(roh, tag, jetzt=None) -> int | None:
    zp = _zeitpunkt(roh, tag)
    if zp is None:
        return None
    return int((zp - (jetzt or uhr.jetzt())).total_seconds() // 60)


def stufe(roh, tag, jetzt=None) -> int:
    """0 = außerhalb der Vorwarnung, 1–3 = im Fenster (3 = Neon), −1 = vorbei."""
    r = rest_minuten(roh, tag, jetzt)
    if r is None:
        return 0
    if r < 0:
        return STUFE_VORBEI
    v = vorwarnung(roh)
    if r > v:
        return 0
    anteil = 1.0 if v == 0 else 1 - r / v
    return 1 + sum(anteil >= a for a in STUFEN_AB)


def rolle(st: int, unv: bool = False) -> str:
    """Schrift-Rolle der Stufe; uncommitted = blass (leise rote Linie)."""
    r = ROLLEN.get(st, ROLLEN[0])
    return r + "_blass" if unv else r


def flaeche(st: int) -> bool:
    return st >= FLAECHE_AB


def rest_kurz(roh, tag, jetzt=None) -> str:
    """„in 2 T", „in 5 h", „in 20 min", „vorbei"."""
    r = rest_minuten(roh, tag, jetzt)
    if r is None:
        return ""
    if r < 0:
        return "vorbei"
    if r < 60:
        return "in %d min" % r
    if r < 24 * 60:
        return "in %d h" % (r // 60)
    return "in %d T" % (r // (24 * 60))


def zeigen(t, jetzt=None) -> bool:
    """Steht die (normierte) Deadline in den Ansichten? (VORBEI_ZEIGEN)"""
    return VORBEI_ZEIGEN or stufe(t["roh"], t["tag"], jetzt) != STUFE_VORBEI


def _hm(m: int) -> str:
    return "%02d:%02d" % (m // 60, m % 60)


# ── Texte je Ansicht ───────────────────────────────────────────────────
def a_text(t: dict, jetzt=None) -> str:
    """A: „⚑ 23:59 Analysis HÜ · in 2 T"."""
    rest = rest_kurz(t["roh"], t["tag"], jetzt)
    return "%s %s %s%s" % (ZEICHEN, _hm(t["start"]), t["label"], " · " + rest if rest else "")


def b_text(t: dict, cw: int) -> str:
    """B: „⚑23:59 Titel", schmal „⚑Titel"."""
    zeit = _hm(t["start"]) + " " if cw >= 10 else ""
    return ZEICHEN + zeit + t["label"]


def c_text(t: dict, breite: int, zeichen: str = ZEICHEN) -> str:
    """C: der Text am Anfang der Linie („⚑ 23:59 Titel "), schmal ohne
    Leerzeichen hinter dem Zeichen."""
    if breite >= 22:
        return "%s %s %s " % (zeichen, _hm(t["start"]), t["label"])
    return "%s%s %s " % (zeichen, _hm(t["start"]), t["label"])


# ── C: die hingemalte Deadline ─────────────────────────────────────────
def c_zeichnen(lw, y0: int, n: int, lo: int, m: int, x: int, breite: int,
               deadlines: list, sel=None, kuerzen=None, text_breite=None,
               akzent: str = "k_akzent", jetzt=None) -> None:
    """Die Deadlines EINES Tages über die Spalte (x, breite) der Zeitachse
    (Zeilen y0…y0+n-1, Zeile k = Minute lo + k*m). Liegt eine davor/danach,
    steht sie am oberen/unteren Rand mit ▲/▼. Zwei in derselben Zeile:
    die zweite rückt eine Zeile weiter. Über allem: nur diese Zeile wird
    überschrieben, Blöcke darunter bleiben erkennbar."""
    if n < 1 or breite < 2:
        return
    belegt: set = set()
    for t in sorted(deadlines, key=lambda t: t["start"]):
        s = t["start"]
        if s < lo:
            k, zeichen = 0, "▲"
        elif s >= lo + n * m:
            k, zeichen = n - 1, "▼"
        else:
            k, zeichen = (s - lo) // m, ZEICHEN
        schritt = -1 if k == n - 1 else 1
        for _ in range(n):
            if k not in belegt:
                break
            k = min(n - 1, max(0, k + schritt))
        belegt.add(k)
        st = stufe(t["roh"], t["tag"], jetzt)
        text = c_text(t, breite, zeichen)
        platz = breite - LINIE_MIN if breite > LINIE_MIN + 8 else breite
        text = kuerzen(text, platz) if kuerzen else text[:platz]
        tb = text_breite(text) if text_breite else len(text)
        linie = (LINIE_UNV if t.get("unv") else LINIE) * max(0, breite - tb)
        y = y0 + k
        if sel is not None and t["roh"] is sel:            # gewählt: Akzent, deckend
            lw.setze(y, x, text + linie, akzent + "_inv")
            continue
        r = rolle(st, t.get("unv"))
        if flaeche(st) and not t.get("unv"):
            lw.setze(y, x, text, r + "_inv")
            lw.setze(y, x + tb, linie, r)
        else:
            lw.setze(y, x, text + linie, r)
