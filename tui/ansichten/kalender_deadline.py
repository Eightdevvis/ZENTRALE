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

Modus Muss | Soll (24.10.2026, Taste S). Sasha: „KEINE DOPPELTEN deadlines
im kalender, ein modus, in dem man soll und muss umschalten kann". Eine
Deadline hat ihre Muss-Zeit (`time`) und optional eine Soll-Zeit (API:
`soll_abstand` Minuten ≤ 0, `soll_zeit` dieses Vorkommens). Im Soll-Modus
legt soll_anwenden() jede solche Deadline auf ihren Soll-Tag/ihre Soll-Zeit
um — VOR dem Normieren, so zeichnen A/B/C, Auswahl und Leuchten sie
überall gleich und nie doppelt. Die Kopie trägt `muss_tag`/`muss_time` und
`_echt` (den API-Eintrag: die Werkzeuge ändern immer das Original).

Soll verpasst (25.10.2026). Sasha: Muss Do 12:00, Soll Fr davor schon
vorbei — im Soll-Modus stand in der Woche nur das Soll fürs NÄCHSTE Blatt,
das Blatt in Arbeit fehlte. Ist die Soll-Zeit eines Vorkommens vorbei, die
Muss-Zeit aber noch nicht, bleibt es im Soll-Modus an seiner Muss-Stelle,
markiert mit VERPASST_TEXT. Nach Muss wieder am Soll-Tag (Vergangenheit).
Weil das von der Uhrzeit abhängt, tragen die Daten `_soll_gilt_bis` (der
nächste Umschlag); die Bedienung holt danach neu (Gefahrzone 1).
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
MUSS, SOLL = "muss", "soll"
SOLL_TAGE = 28                         # wie core SOLL_HOECHSTENS: so weit holt die TUI voraus
VERPASST_TEXT = "soll verpasst"        # Markierung (A, B, C, Ansehen); Sasha entscheidet
WT = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def ist(t) -> bool:
    """Ein API-Eintrag oder ein normierter Eintrag der Ansichten."""
    if not isinstance(t, dict):
        return False
    return bool(t.get("deadline")) or t.get("typ") == TYP


def soll_abstand(roh) -> int | None:
    v = (roh or {}).get("soll_abstand")
    if isinstance(v, int) and not isinstance(v, bool) and -SOLL_TAGE * 1440 <= v <= 0:
        return v
    return None


def soll_zeitpunkt(roh, tag) -> datetime | None:
    """Die Soll-Zeit eines Vorkommens: `soll_zeit` der API, sonst Muss +
    soll_abstand; None ohne Soll."""
    if not ist(roh):
        return None
    try:
        return datetime.strptime(str(roh.get("soll_zeit")), "%Y-%m-%dT%H:%M")
    except ValueError:
        pass
    zp, s = _zeitpunkt(roh, tag), soll_abstand(roh)
    return None if zp is None or s is None else zp + timedelta(minutes=s)


def verpasst(soll: datetime | None, muss: datetime | None, jetzt: datetime) -> bool:
    """Soll vorbei, Muss noch nicht."""
    return soll is not None and muss is not None and soll < jetzt < muss


def _soll_kopie(e, iso, jetzt):
    """(Tag, Kopie) oder None (keine Soll-Zeit). Die Kopie steht zur
    Soll-Zeit am Soll-Tag — ist das Soll verpasst, zur Muss-Zeit am Muss-Tag
    mit `soll_verpasst`. Dazu der nächste Zeitpunkt, an dem sich das ändert
    (oder None)."""
    if not isinstance(e, dict) or e.get("spanning"):
        return None
    zp, muss = soll_zeitpunkt(e, iso), _zeitpunkt(e, iso)
    if zp is None or muss is None:
        return None
    kopie = dict(e, muss_tag=iso, muss_time=e.get("time"))
    kopie["_echt"] = e
    if verpasst(zp, muss, jetzt):
        kopie["soll_verpasst"] = True
        return iso, kopie, muss
    kopie["time"] = zp.strftime("%H:%M")
    return zp.date().isoformat(), kopie, (zp if jetzt < zp else None)


def soll_anwenden(daten: dict, spaeter: dict | None = None, jetzt=None) -> None:
    """Soll-Modus: jede Deadline mit Soll-Zeit wandert (an Ort und Stelle)
    von ihrem Muss-Tag auf den Soll-Tag zur Soll-Uhrzeit — außer ihr Soll
    ist verpasst (siehe oben). `spaeter`: die `days` NACH dem Ende der
    Daten (die TUI holt SOLL_TAGE voraus) — von dort kommen nur Deadlines,
    deren Soll-Tag in die Daten fällt. Setzt `_soll_gilt_bis` (ISO-Zeit des
    nächsten Umschlags, oder weg)."""
    tage = daten.get("days") if isinstance(daten, dict) else None
    if not isinstance(tage, dict):
        return
    jetzt = jetzt or uhr.jetzt()
    wandern, umschlag = [], []
    for iso, es in list(tage.items()):
        if not isinstance(es, list):
            continue
        bleibt = []
        for e in es:
            k = _soll_kopie(e, iso, jetzt)
            (wandern.append(k) if k else bleibt.append(e))
        tage[iso] = bleibt
    ende = str(daten.get("end") or max(tage, default=""))
    for iso, es in (spaeter or {}).items():
        if iso in tage or not isinstance(es, list):
            continue
        for e in es:
            k = _soll_kopie(e, iso, jetzt)
            if k and k[0] <= ende:
                wandern.append(k)
            elif k and k[2] is not None:
                umschlag.append(k[2])     # wird später verpasst: dann neu holen
    for tag, kopie, wechsel in wandern:
        tage.setdefault(tag, []).append(kopie)
        if wechsel is not None:
            umschlag.append(wechsel)
    if umschlag:
        daten["_soll_gilt_bis"] = min(umschlag).isoformat(timespec="minutes")
    else:
        daten.pop("_soll_gilt_bis", None)


def veraltet(daten, jetzt=None) -> bool:
    """Ist ein Soll seit dem Holen verpasst oder ein verpasstes Muss vorbei?"""
    bis = daten.get("_soll_gilt_bis") if isinstance(daten, dict) else None
    if not bis:
        return False
    try:
        return (jetzt or uhr.jetzt()) >= datetime.fromisoformat(bis)
    except ValueError:
        return False


def modus_anwenden(daten: dict, modus: str, spaeter: dict | None = None, jetzt=None) -> None:
    """daten["modus"] setzen (der Kopf zeigt es) und im Soll-Modus umlegen."""
    if not isinstance(daten, dict):
        return
    daten["modus"] = SOLL if modus == SOLL else MUSS
    if daten["modus"] == SOLL:
        soll_anwenden(daten, spaeter, jetzt)


def modus_text(daten) -> str:
    """„muss"/„soll" für den Kopf — leer, wenn die Daten keinen Modus
    tragen (Vorschau, Tests)."""
    m = daten.get("modus") if isinstance(daten, dict) else None
    return m if m in (MUSS, SOLL) else ""


def wann(zp: datetime) -> str:
    """Wochentag, Datum, Uhrzeit: „Di 21.10. 18:00“."""
    return "%s %s" % (WT[zp.weekday()], zp.strftime("%d.%m. %H:%M"))


def soll_muss_zeilen(roh, tag, jetzt=None) -> list:
    """Für das Ansehen-Fenster: [„soll Di 21.10. 18:00", „muss Fr 24.10. 12:00"]
    — leer ohne Soll-Zeit; verpasst: „soll Di 21.10. 18:00 · soll verpasst"."""
    soll, muss = soll_zeitpunkt(roh, tag), _zeitpunkt(roh, tag)
    if soll is None or muss is None:
        return []
    marke = " · " + VERPASST_TEXT if verpasst(soll, muss, jetzt or uhr.jetzt()) else ""
    return ["soll %s%s" % (wann(soll), marke), "muss %s" % wann(muss)]


def dl(t) -> dict:
    """Der Eintrag, nach dessen Zeit eine normierte Deadline leuchtet: im
    Soll-Modus die Kopie zur Soll-Zeit, sonst der API-Eintrag."""
    return t.get("dl") or t["roh"]


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
    return VORBEI_ZEIGEN or stufe(dl(t), t["tag"], jetzt) != STUFE_VORBEI


def _hm(m: int) -> str:
    return "%02d:%02d" % (m // 60, m % 60)


# ── Texte je Ansicht ───────────────────────────────────────────────────
def a_text(t: dict, jetzt=None) -> str:
    """A: „⚑ 23:59 Analysis HÜ · in 2 T"; im Soll-Modus dahinter winzig
    „· muss Fr 12:00" (nie eine zweite Zeile), Soll verpasst: „· soll verpasst"."""
    rest = rest_kurz(dl(t), t["tag"], jetzt)
    aus = "%s %s %s%s" % (ZEICHEN, _hm(t["start"]), t["label"], " · " + rest if rest else "")
    if ist_verpasst(t):
        return aus + " · " + VERPASST_TEXT
    muss = _zeitpunkt(t["roh"], t.get("muss_tag") or "") if t.get("muss_tag") else None
    return aus + (" · muss %s %s" % (WT[muss.weekday()], muss.strftime("%H:%M")) if muss else "")


def ist_verpasst(t: dict) -> bool:
    """Eine normierte Deadline, deren Soll verpasst ist (soll_anwenden)."""
    return bool((t.get("dl") or {}).get("soll_verpasst"))


def _marke(t: dict) -> str:
    return " · " + VERPASST_TEXT if ist_verpasst(t) else ""


def b_text(t: dict, cw: int) -> str:
    """B: „⚑23:59 Titel", schmal „⚑Titel" (Markierung hinten, fällt beim
    Kürzen zuerst weg)."""
    zeit = _hm(t["start"]) + " " if cw >= 10 else ""
    return ZEICHEN + zeit + t["label"] + _marke(t)


def c_text(t: dict, breite: int, zeichen: str = ZEICHEN) -> str:
    """C: der Text am Anfang der Linie („⚑ 23:59 Titel "), schmal ohne
    Leerzeichen hinter dem Zeichen."""
    if breite >= 22:
        return "%s %s %s%s " % (zeichen, _hm(t["start"]), t["label"], _marke(t))
    return "%s%s %s%s " % (zeichen, _hm(t["start"]), t["label"], _marke(t))


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
        st = stufe(dl(t), t["tag"], jetzt)
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
