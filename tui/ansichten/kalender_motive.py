"""Tagesphasen als leiser Hintergrund der Woche (Ansicht C) — reine Funktionen.

Sasha, 10.10.2026: „fürs coming down ein paar sterne, wolken usw eingemalt
wie ein nachthimmel, ab 10 uhr ein par z z z für schlafsymbole usw … eine
leichte hintergrund ebene". Eine Phase (Ebene `rhythmus`, Feld `motiv`, im
Kern core/kalender_rhythmus.py) ist darum KEIN Block: sie nimmt keine Bahn,
ist nicht wählbar und füllt nur ihren Zeitbereich in der Tagesspalte mit
wenigen, schmalen Zeichen — VOR den Terminen gezeichnet, die darüber liegen
(kalender_ansichten._c_achse); die Punktlinien lassen den Zeichen Platz
(Regler PUNKTLINIE_WEICHT).

Alles, was nach Geschmack ist, steht in MUSTER und den Reglern darunter —
Sasha stellt die Optik um, ohne die Zeichen-Logik anzufassen. Die Farben je
Motiv stehen in farben.MOTIV_FARBEN (Rolle „k_m_<motiv>").

Nur einspaltige Zeichen (keine Emoji): ein breites Zeichen verschöbe die
Spalten. Gestreut wird deterministisch (crc32 aus Tag, Uhrzeit der Zeile und
Spalte), damit das Muster beim Neuzeichnen und Scrollen stillsteht.
"""
from __future__ import annotations

import zlib
from datetime import date, timedelta

EBENE = "rhythmus"          # wie core/kalender_rhythmus.EBENE

# ── Regler ─────────────────────────────────────────────────────────────
# Je Motiv: welche Zeichen (Häufigkeit = wie oft ein Zeichen im Text steht;
# nur Zeichen, die gängige Terminal-Schriften haben — DejaVu Sans Mono hat
# z. B. kein ⋔ und kein ⁖, tests/test_kalender_motive.py prüft die Breite)
# und wie dicht (Anteil der freien Zellen im Schachbrett, 0…1). Ein neues
# Motiv im Kern (kalender_rhythmus.MOTIVE) → hier eine Zeile; fehlt sie,
# nimmt es RUECKFALL.
MUSTER = {
    "nachthimmel": {"zeichen": "⋆⋆✦⋆✧⋆☁✦☾", "dichte": 0.16},
    "schlaf":      {"zeichen": "zzZᶻᶻz",     "dichte": 0.11},
    "essen":       {"zeichen": "∘◦∪◦∘",      "dichte": 0.13},
    "sonne":       {"zeichen": "✺✹✶✹",       "dichte": 0.13},
    "fokus":       {"zeichen": "⋄▫⋄",        "dichte": 0.08},
    "sport":       {"zeichen": "⌃∧⌃",        "dichte": 0.10},
    "ruhe":        {"zeichen": "~~∼",        "dichte": 0.09},
    "unterwegs":   {"zeichen": "›⇢⋯›",       "dichte": 0.10},
}
RUECKFALL = {"zeichen": "∙", "dichte": 0.08}
# Nur jede zweite Zelle (Schachbrett) kommt überhaupt in Frage — so stehen
# nie zwei Zeichen direkt nebeneinander und das Muster bleibt luftig.
SCHACHBRETT = True
# Punktlinien (volle Stunden) lassen den Zeichen einer Phase Platz. Aus =
# die Linie geht durch und deckt sie zu — dann ist eine halbe Stunde, die
# auf der vollen Stunde liegt (essen 10:00–10:30), gar nicht zu sehen.
PUNKTLINIE_WEICHT = True
# Eine Phase ohne Ende („gegen 10 hungrig"): so lange zeigt C sie.
OHNE_ENDE_MINUTEN = 60
# Ansicht A: leiser Hinweis im Tageskopf („☾ 21:30 · ᶻ 23:00"), links vom
# Datum, ohne eigene Zeile. Sasha hat nur C bestellt — hier abschaltbar.
A_HINWEIS = True
# Das Zeichen, das in A für ein Motiv steht (erstes aus MUSTER, wenn fehlt).
A_ZEICHEN = {"nachthimmel": "☾", "schlaf": "ᶻ", "essen": "∘", "sonne": "✹"}


def rolle(motiv) -> str:
    """Palettenrolle eines Motivs (farben.MOTIV_FARBEN → C["k_m_…"])."""
    return "k_m_" + (motiv if motiv in MUSTER else "rueckfall")


def muster(motiv) -> dict:
    return MUSTER.get(motiv) or RUECKFALL


def zeichen_a(motiv) -> str:
    return A_ZEICHEN.get(motiv) or muster(motiv)["zeichen"][0]


# ── Phasen aus den API-Daten ───────────────────────────────────────────
def _min(s) -> int | None:
    if not isinstance(s, str) or ":" not in s:
        return None
    try:
        h, m = s.strip().split(":", 1)
        v = int(h) * 60 + int(m)
    except ValueError:
        return None
    return v if 0 <= v <= 24 * 60 else None


def ist_phase(e) -> bool:
    return isinstance(e, dict) and e.get("layer") == EBENE


def _roh(daten, iso) -> list:
    tage = daten.get("days") if isinstance(daten, dict) else None
    liste = tage.get(iso) if isinstance(tage, dict) else None
    return [e for e in (liste if isinstance(liste, list) else [])
            if ist_phase(e) and not (e.get("deaktiviert") or e.get("ausfall"))]


def _ende(e, s) -> tuple:
    """(ende in Minuten, über Nacht?) — Ende vor Beginn heißt Folgetag
    (`ueber_nacht` von der API; zur Sicherheit auch selbst erkannt)."""
    en = _min(e.get("ende"))
    if en is None:
        return min(24 * 60, s + OHNE_ENDE_MINUTEN), False
    return en, bool(e.get("ueber_nacht")) or en < s


def tag_phasen(daten, tag: date) -> list:
    """Die Phasen, die an `tag` zu sehen sind: [(von, bis, motiv, eintrag)]
    in Minuten des Tages. Eine Phase über Mitternacht (Schlaf 23:00–07:00)
    steht in den Daten nur am Tag ihres Beginns: dort läuft sie bis 24:00,
    am Folgetag von 0:00 bis zu ihrem Ende."""
    out = []
    for e in _roh(daten, tag.isoformat()):
        s = _min(e.get("time"))
        if s is None:
            continue
        en, nacht = _ende(e, s)
        out.append((s, 24 * 60 if nacht else en, e.get("motiv"), e))
    for e in _roh(daten, (tag - timedelta(days=1)).isoformat()):
        s = _min(e.get("time"))
        if s is None:
            continue
        en, nacht = _ende(e, s)
        if nacht and en > 0:
            out.append((0, en, e.get("motiv"), e))
    out.sort(key=lambda p: (p[0], p[1]))
    return [p for p in out if p[1] > p[0]]


# ── Zeichnen ───────────────────────────────────────────────────────────
def _streu(*teile) -> int:
    return zlib.crc32(":".join(str(t) for t in teile).encode("utf-8"))


def zelle(tag_iso: str, minute: int, spalte: int, motiv, takt: int = 30) -> str | None:
    """Das Zeichen für eine Zelle (oder None = leer). Hängt nur an Tag,
    Uhrzeit der Zeile und Spalte in der Tagesspalte — scrollt man, wandert
    das Muster mit der Uhrzeit, nicht mit dem Bildschirm."""
    m = muster(motiv)
    if SCHACHBRETT and (spalte + minute // max(1, takt)) % 2:
        return None
    h = _streu(tag_iso, minute, spalte, motiv)
    if (h % 1000) >= m["dichte"] * 1000:
        return None
    z = m["zeichen"]
    return z[(h // 1000) % len(z)] if z else None


def zeichne_spalte(lw, y0: int, n: int, lo: int, takt: int, x: int, breite: int,
                   tag: date, phasen: list) -> None:
    """Phasen eines Tages in die Leinwand: Zeilen y0…y0+n-1 stehen für die
    Minuten lo, lo+takt, … ; die Tagesspalte beginnt bei x und ist `breite`
    breit. Später beginnende Phasen liegen über früheren (überlappen sich
    zwei, gewinnt die jüngere)."""
    iso = tag.isoformat()
    for k in range(n):
        a, b = lo + k * takt, lo + (k + 1) * takt
        motiv = None
        for s, e, mo, _roh_e in phasen:
            if s < b and e > a:                 # Zeile überlappt die Phase
                motiv = mo
        if motiv is None:
            continue
        for c in range(breite):
            ch = zelle(iso, a, c, motiv, takt)
            if ch:
                lw.setze(y0 + k, x + c, ch, rolle(motiv))


def a_hinweis(daten, tag: date) -> list:
    """[(text, rolle)] für den Tageskopf in A: „☾ 21:30 ᶻ 23:00" — nur
    Phasen, die an dem Tag BEGINNEN; leer, wenn A_HINWEIS aus ist."""
    if not A_HINWEIS:
        return []
    teile = []
    for e in _roh(daten, tag.isoformat()):
        s = _min(e.get("time"))
        if s is None:
            continue
        teile.append((s, "%s %02d:%02d" % (zeichen_a(e.get("motiv")), s // 60, s % 60),
                      rolle(e.get("motiv"))))
    teile.sort()
    return [(t, r) for _s, t, r in teile]
