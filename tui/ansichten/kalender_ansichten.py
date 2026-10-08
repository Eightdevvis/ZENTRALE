"""Kalender-Ansichten A/B/C für die TUI — reine Funktionen, kein curses.

Warum ein eigenes Modul: tui/zentrale_tui.py ist ein eingefrorener Riese
(memory/system/bauplan_kern.md, „Altlast: Riesen"). Die drei Entwürfe
(Tagesliste, Monatsraster, Woche als Zeitachse) kommen deshalb NICHT in
draw_calendar, sondern hierher — als Funktionen, die man ohne Terminal testen
und in einer Vorschau anschauen kann (scripts/kalender_vorschau.py).

Eingabe ist genau das, was /api/calendar liefert ({today, ref, start, end,
first?, last?, days:{iso:[einträge]}}), damit es mit dem alten JSON-Speicher
und dem neuen .ics-Speicher gleich läuft — die API-Form ist die Grenze.

Ausgabe: eine Liste von Zeilen, jede Zeile eine Liste von (text, rolle).
Rollen sind die Wörter der TUI-Palette (C["faint"], C["acc"] …). Endet eine
Rolle auf "_inv", ist die Fläche gemeint (Farbe als Hintergrund) — in curses
heißt das C[basis] | A_REVERSE. Keine Zeile ist je breiter als `breite`:
alles läuft über eine Leinwand, die am Rand abschneidet.

Was die Farben bedeuten, steht an EINER Stelle (ROLLE unten), damit Sasha
die Optik umstellen kann, ohne die Zeichen-Logik anzufassen.
"""
from __future__ import annotations

import math
import unicodedata
from datetime import date, timedelta

# ── Ansichten und Taste v ──────────────────────────────────────────────
ANSICHTEN = ("A", "B", "C")
ANSICHT_NAMEN = {"A": "tagesliste", "B": "monat", "C": "woche"}
# Welche /api/calendar-Form jede Ansicht braucht. A will „ab heute" mehr als
# eine Woche zeigen und einen ganzen Mini-Monat färben → Monatsdaten.
DATENANSICHT = {"A": "month", "B": "month", "C": "week"}
# Wie weit ←→ springt. A zeigt nur ein paar Tage ab `ref` → tageweise.
SCHRITT = {"A": "tag", "B": "monat", "C": "woche"}

INV = "_inv"

# Semantik → Palettenrolle. Die Entwürfe haben mehr Farbtöne als die TUI;
# hier wird entschieden, welche TUI-Rolle einen Ton vertritt.
ROLLE = {
    "rahmen": "faint",      # Kastenlinien, Trenner, Punkt-Raster
    "titel": "acc",         # Kastentitel, Tagesköpfe
    "heute": "warn",        # heutiger Tag (Entwurf: rot/fett)
    "zeit": "faint",        # „10:00–18:00" in der Liste
    "routine": "dim",       # wiederkehrend: normaler Text
    "termin": "bright",     # Einmal-Termin: hervorgehoben
    "ganztags": "net",      # ganztägig ohne Spanne (Entwurf: blau)
    "spanne": "span",       # mehrtägig (Entwurf: bernstein)
    "werktag": "dim",       # Wochentags-Köpfe im Raster
    "wochenende": "acc",    # Sa/So im Raster
    "leer": "faint",        # „—" an leeren Tagen, „+2" bei Überlauf
    "aus": "faint",         # deaktiviert / Ausfall (nur mit erledigte=True)
    "block_routine": "faint",   # Zeitachse: Fläche einer Routine (grau)
    "block_termin": "net",      # Zeitachse: Fläche eines Einmal-Termins
    "c_wochenende": "amber",    # Zeitachse: Sa/So-Köpfe
    "a_akzent": "kal",          # A (calcurse): Titel, Datum, KW, Statuszeile
    "a_aktiv": "kal",           # A: Rahmen des aktiven Kastens
    "zyklus": "cyc",            # Zyklus-Tönung (aus dem »periode«-Graphen)
}
# Zeitachse: nebeneinanderliegende Spannen müssen unterscheidbar sein
# (Entwurf: Messe bernstein, Berlin grün) → reihum vergeben.
SPANNEN_FARBEN = ("span", "acc", "graph", "amber")

WT = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")

Zeile = list  # [(text, rolle), …]


def naechste_ansicht(aktuell: str | None) -> str:
    """Taste v: A → B → C → A. Den alten Kalender als vierte Station gibt es
    seit 07.10.2026 nicht mehr (alle drei sind bedienbar). Unbekanntes fängt
    bei A an, statt zu crashen."""
    if aktuell not in ANSICHTEN:
        return ANSICHTEN[0]
    return ANSICHTEN[(ANSICHTEN.index(aktuell) + 1) % len(ANSICHTEN)]


def tasten_hinweis(ansicht: str) -> str:
    """Fußzeile je Ansicht — nur Tasten, die beim Einhängen wirklich gebunden
    sind. A/B/C sind reine Anzeige: bearbeitet wird im jetzigen Kalender."""
    ziel = ANSICHT_NAMEN[naechste_ansicht(ansicht)]
    # Alle drei bedienbar wie calcurse (kalender_bedienung.py); gleich sind
    # a/e/d/r/c/p/g/enter, nur das Bewegen unterscheidet sich.
    gleich = "a neu · e ändern · d löschen · r wiederholen · enter ansehen · c/p kopieren · g gehe zu"
    if ansicht == "A":
        return "↑↓ termin · ←→ tag · %s · tab kasten · v %s" % (gleich, ziel)
    if ansicht == "B":
        return "←→ tag · ↑↓ woche · tab termin · %s · m/M monat · v %s" % (gleich, ziel)
    if ansicht == "C":
        return "↑↓ termin · ←→ tag · %s · w/W woche · v %s" % (gleich, ziel)
    return "v %s" % ziel


def zeichne(ansicht: str, daten, breite: int, hoehe: int,
            erledigte: bool = False, auswahl: dict | None = None) -> list:
    """Einstieg für die TUI: zeichnet die gewählte Ansicht in breite×hoehe.
    `auswahl` (kalender_bedienung.Bedienung.auswahl) hebt Tag/Termin/Kasten
    hervor — bisher nur in A, B/C folgen in Etappe 2."""
    if ansicht == "B":
        return ansicht_b(daten, breite, hoehe, erledigte=erledigte, auswahl=auswahl)
    if ansicht == "C":
        return ansicht_c(daten, breite, hoehe, erledigte=erledigte, auswahl=auswahl)
    return ansicht_a(daten, breite, hoehe, erledigte=erledigte, auswahl=auswahl)


# ── Text-Breite und Leinwand ───────────────────────────────────────────
def _zb(ch: str) -> int:
    """Spalten eines Zeichens im Terminal: Kombinierer 0, CJK/Emoji 2."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_breite(s: str) -> int:
    return sum(_zb(c) for c in s)


def kuerzen(text: str, n: int) -> str:
    """Auf n Spalten kürzen; was abgeschnitten wird, endet mit „…" — ein
    abgehackter Titel sieht sonst aus wie ein anderer Termin."""
    if n <= 0:
        return ""
    if text_breite(text) <= n:
        return text
    out, b = [], 0
    for ch in text:
        w = _zb(ch)
        if b + w > n - 1:
            break
        out.append(ch)
        b += w
    return "".join(out).rstrip() + "…"     # „Tag der …" sähe nach Lücke aus


def zeilen_breite(zeile) -> int:
    return sum(text_breite(t) for t, _r in zeile)


class Leinwand:
    """Zeichenraster breite×hoehe. Alles, was darüber hinaus geschrieben
    wird, fällt weg — so kann keine Ansicht je breiter werden als erlaubt,
    egal wie schmal es wird. Ein breites Zeichen belegt zwei Zellen, die
    zweite bleibt leer (""), damit die Spaltenzählung stimmt."""

    LEER = (" ", "dim")

    def __init__(self, breite: int, hoehe: int):
        self.b = max(0, int(breite))
        self.h = max(0, int(hoehe))
        self.z = [[self.LEER] * self.b for _ in range(self.h)]

    def setze(self, y: int, x: int, text: str, rolle: str) -> int:
        if not 0 <= y < self.h:
            return x
        reihe = self.z[y]
        for ch in text:
            w = _zb(ch)
            if w == 0:
                continue
            if x < 0:
                x += w
                continue
            if x + w > self.b:
                break
            # Halb überschriebene breite Zeichen aufräumen, sonst verrutscht
            # die Zeile um eine Spalte.
            if reihe[x][0] == "" and x > 0:
                reihe[x - 1] = self.LEER
            letzte = reihe[x + w - 1][0]
            if letzte and _zb(letzte) == 2 and x + w < self.b:
                reihe[x + w] = self.LEER
            reihe[x] = (ch, rolle)
            if w == 2:
                reihe[x + 1] = ("", rolle)
            x += w
        return x

    def zeilen(self) -> list:
        """Läufe gleicher Rolle zusammenfassen; Leerraum am Zeilenende fällt
        weg (der Hintergrund ist ohnehin leer)."""
        out = []
        for reihe in self.z:
            ende = len(reihe)
            while ende and reihe[ende - 1] == self.LEER:
                ende -= 1
            zeile: list = []
            for ch, rolle in reihe[:ende]:
                if zeile and zeile[-1][1] == rolle:
                    zeile[-1] = (zeile[-1][0] + ch, rolle)
                else:
                    zeile.append((ch, rolle))
            out.append(zeile)
        return out


def _kasten(lw: Leinwand, y: int, x: int, w: int, h: int, titel: str = ""):
    """Kasten wie in den Entwürfen: ┌─ TITEL ───┐, Titel in Titelfarbe."""
    if w < 2 or h < 2:
        return
    r = ROLLE["rahmen"]
    lw.setze(y, x, "┌" + "─" * (w - 2) + "┐", r)
    for i in range(1, h - 1):
        lw.setze(y + i, x, "│", r)
        lw.setze(y + i, x + w - 1, "│", r)
    lw.setze(y + h - 1, x, "└" + "─" * (w - 2) + "┘", r)
    if titel and w > 6:
        lw.setze(y, x + 2, kuerzen(" " + titel.upper() + " ", w - 4),
                 ROLLE["titel"])


def _zu_klein(breite: int, hoehe: int) -> list:
    lw = Leinwand(breite, hoehe)
    lw.setze(0, 0, kuerzen("zu schmal", breite), ROLLE["leer"])
    return lw.zeilen()


# ── Zeiten und Einträge ────────────────────────────────────────────────
def _min(s) -> int | None:
    """'17:45' → 1065. Alles andere → None (kaputte Daten zeichnen wir
    als ganztags, statt abzustürzen)."""
    if not isinstance(s, str) or ":" not in s:
        return None
    try:
        h, m = s.strip().split(":", 1)
        v = int(h) * 60 + int(m)
    except ValueError:
        return None
    return v if 0 <= v <= 24 * 60 else None


def _zeitspanne(s) -> tuple:
    """'10:00' → (600, None); '10:00-18:00' / '10:00–18:00' → (600, 1080).
    Die Bereichsform gibt es heute nur, wenn jemand sie per spantime
    speichert — wir lesen sie, damit „von–bis pro Spannentag" ohne neue API
    sichtbar wird, sobald der Speicher sie hergibt."""
    if not isinstance(s, str):
        return None, None
    for sep in ("–", "-", "—"):
        if sep in s:
            a, b = s.split(sep, 1)
            return _min(a), _min(b)
    return _min(s), None


def _hm(m: int) -> str:
    return "%02d:%02d" % (m // 60, m % 60)


def _hm_kurz(m: int) -> str:
    """Volle Stunden als „10", sonst „10:30" — wie im Spannen-Kasten des
    Entwurfs („10–18 · 09–17")."""
    return "%02d" % (m // 60) if m % 60 == 0 else _hm(m)


def _normiere(e: dict, iso: str, aus: bool) -> dict:
    label = str(e.get("label") or "?")
    s, en = _zeitspanne(e.get("time"))
    if en is None:
        en = _min(e.get("ende"))
    spanne = bool(e.get("spanning"))
    erster, letzter = bool(e.get("span_first")), bool(e.get("span_last"))
    if spanne and erster and letzter:
        spanne = False                 # eintägige „Spanne" = normaler Termin
    # Eine einzelne Uhrzeit am LETZTEN Tag einer Spanne ist ihr Ende
    # („Berlin bis So 14:00"), am ersten ihr Anfang. Die API kennt pro Tag
    # nur EIN Uhrzeit-Feld; das ist die naheliegende Lesart davon.
    if spanne and letzter and not erster and s is not None and en is None:
        s, en = None, s
    if s is not None and en is not None and en <= s:
        en = None
    return {
        "label": label, "start": s, "ende": en, "spanne": spanne,
        "erster": erster, "letzter": letzter, "tag": iso,
        "von": e.get("von") if isinstance(e.get("von"), str) else iso,
        "bis": e.get("bis") if isinstance(e.get("bis"), str) else iso,
        "key": (e.get("von"), e.get("bis"), label, e.get("layer")),
        "routine": bool(e.get("recurring")), "aus": aus,
        "ausfall": bool(e.get("ausfall")),
        # Der API-Eintrag selbst: die Werkzeuge (kalender_werkzeuge.py) arbeiten
        # mit DERSELBEN Liste in DERSELBEN Reihenfolge wie die Ansicht.
        "roh": e,
    }


def _tag_eintraege(daten: dict, iso: str, erledigte: bool) -> list:
    """Einträge eines Tages, normiert. Deaktiviertes und Ausfälle bleiben —
    wie im alten Kalender — versteckt, solange `erledigte` aus ist."""
    tage = daten.get("days")
    roh = tage.get(iso) if isinstance(tage, dict) else None
    out = []
    for e in roh if isinstance(roh, list) else []:
        if not isinstance(e, dict):
            continue
        aus = bool(e.get("deaktiviert") or e.get("ausfall"))
        if aus and not erledigte:
            continue
        out.append(_normiere(e, iso, aus))
    # Spannen zuerst (sie rahmen den Tag), dann Ganztägiges, dann nach Zeit.
    out.sort(key=lambda t: (not t["spanne"], t["start"] is not None,
                            t["start"] if t["start"] is not None else 0))
    return out


def _vonbis(t: dict, kurz: bool = False) -> str:
    """Die „von–bis"-Angabe eines Eintrags an seinem Tag. Bei Spannen zeigen
    Pfeile, dass es über den Tag hinaus weitergeht."""
    f = _hm_kurz if kurz else _hm
    s, e = t["start"], t["ende"]
    if s is not None and e is not None:
        return "%s–%s" % (f(s), f(e))
    if t["spanne"]:
        if s is not None:
            return "%s →" % f(s)
        if e is not None:
            return "→ %s" % f(e)
        return "↔" if kurz else "↔ ganzer Tag"
    if s is not None:
        return f(s)
    if e is not None:
        return "bis " + f(e)
    return "ganzt." if kurz else "ganztags"


def _rolle(t: dict) -> str:
    if t["aus"]:
        return ROLLE["aus"]
    if t["spanne"]:
        return ROLLE["spanne"]
    if t["start"] is None and t["ende"] is None:
        return ROLLE["ganztags"]
    return ROLLE["routine"] if t["routine"] else ROLLE["termin"]


def _datum(s) -> date | None:
    try:
        return date.fromisoformat(s) if isinstance(s, str) else None
    except ValueError:
        return None


def _rahmen(daten: dict) -> tuple:
    """(heute, start, ende) aus den API-Daten, defensiv: fehlt etwas, wird
    aus den vorhandenen Tagen geschlossen."""
    tage = daten.get("days") if isinstance(daten.get("days"), dict) else {}
    isos = sorted(d for d in (_datum(k) for k in tage) if d)
    heute = (_datum(daten.get("today")) or _datum(daten.get("ref"))
             or _datum(daten.get("start")) or (isos[0] if isos else None)
             or date.today())
    start = _datum(daten.get("start")) or (isos[0] if isos else heute)
    ende = _datum(daten.get("end")) or (isos[-1] if isos else start)
    if ende < start:
        start, ende = ende, start
    return heute, start, ende


def _tage(a: date, b: date):
    while a <= b:
        yield a
        a += timedelta(days=1)


def _spannen(daten: dict, start: date, ende: date, erledigte: bool) -> list:
    """Alle Spannen, die im Datenbereich vorkommen, mit ihren Tagen.
    Schlüssel ist (von, bis, label, layer) — die API hat keine IDs; dieselbe
    Spanne taucht an jedem ihrer Tage als eigene Kopie auf."""
    alle: dict = {}
    for d in _tage(start, ende):
        for t in _tag_eintraege(daten, d.isoformat(), erledigte):
            if not t["spanne"]:
                continue
            sp = alle.setdefault(t["key"], {
                "key": t["key"], "label": t["label"],
                "von": _datum(t["von"]) or d, "bis": _datum(t["bis"]) or d,
                "tage": {}})
            sp["tage"][d] = t
    out = list(alle.values())
    out.sort(key=lambda s: (s["von"], s["bis"], s["label"]))
    return out


# ── A: Tagesliste + Kästen (nach calcurse) ─────────────────────────────
# Sasha, 07.10.2026, mit einem calcurse-Bild daneben: „die calcurse inspired
# ansicht ist ja jetzt nicht wirklich wie die calcurse ansicht". Also wie
# calcurse: Kastentitel mittig IM Kasten mit Trennlinie darunter, der aktive
# Kasten mit Rahmen in Akzentfarbe, je Tag ein Block mit rechtsbündigem
# Datum, Termine zweizeilig („- 14:00 -> 15:00", darunter der Titel),
# Routinen mit „*", Spannen mit calcurse-Pfeilen („18:00 -> ..:.."),
# Mini-Monat mit Kalenderwochen und [heute], unten die Statuszeile mit Uhr
# und nächstem Termin.
WT_LANG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
           "Samstag", "Sonntag")


def _a_rolle(name: str) -> str:
    return ROLLE.get(name, ROLLE["titel"])


def _paneel(lw, y, x, w, h, titel, aktiv=False) -> int:
    """calcurse-Kasten: Titel mittig in der ersten Innenzeile, darunter
    ├───┤. Liefert die erste freie Innenzeile."""
    if w < 4 or h < 4:
        return y + 1
    r = _a_rolle("a_aktiv") if aktiv else ROLLE["rahmen"]
    lw.setze(y, x, "┌" + "─" * (w - 2) + "┐", r)
    for i in range(1, h - 1):
        lw.setze(y + i, x, "│", r)
        lw.setze(y + i, x + w - 1, "│", r)
    lw.setze(y + h - 1, x, "└" + "─" * (w - 2) + "┘", r)
    t = kuerzen(titel, w - 4)
    lw.setze(y + 1, x + (w - text_breite(t)) // 2, t, _a_rolle("a_akzent"))
    lw.setze(y + 2, x, "├" + "─" * (w - 2) + "┤", r)
    return y + 3


def _a_zeit(t: dict) -> str | None:
    """calcurse-Zeitzeile: „14:00 -> 15:00", bei Spannen „18:00 -> ..:..",
    „..:.. -> ..:..", „..:.. -> 14:00". Ganztägiges hat keine (None)."""
    s, e = t["start"], t["ende"]
    if t["spanne"]:
        links = _hm(s) if s is not None else "..:.."
        rechts = _hm(e) if e is not None else "..:.."
        return "%s -> %s" % (links, rechts)
    if s is None and e is None:
        return None
    if e is None:
        return _hm(s)
    if s is None:
        return "..:.. -> " + _hm(e)
    return "%s -> %s" % (_hm(s), _hm(e))


def _a_naechster(daten, ab, ende, jetzt, erledigte):
    """Nächster Termin ab jetzt: (datum, eintrag) oder None."""
    jm = jetzt.hour * 60 + jetzt.minute
    for d in _tage(ab, ende):
        for t in _tag_eintraege(daten, d.isoformat(), erledigte):
            if t["start"] is None or t["aus"]:
                continue
            if d > jetzt.date() or t["start"] >= jm:
                return d, t
    return None


def ansicht_a(daten, breite: int, hoehe: int, erledigte: bool = False,
              jetzt=None, tage: int = 3, auswahl: dict | None = None) -> list:
    """Wie calcurse: links „Termine" (aktiv) mit `tage` Tagen ab `ref`,
    gleich hoch verteilt; rechts „Kalender" und „TODO", unten der rote
    Statusbalken. Unter ~86 Spalten bleibt nur die Terminliste.

    Sasha, 07.10.2026: lieber wenige Tage mit Luft als viele gequetscht —
    für Woche und Monat gibt es B und C."""
    from datetime import datetime
    daten = daten if isinstance(daten, dict) else {}
    if breite < 16 or hoehe < 5:
        return _zu_klein(breite, hoehe)
    lw = Leinwand(breite, hoehe)
    heute, start, ende = _rahmen(daten)
    ref = _datum(daten.get("ref"))
    ab = ref if ref and start <= ref <= ende else (heute if start <= heute <= ende else start)
    jetzt = jetzt or datetime.now()
    if jetzt.date() != heute:          # Vorschau/Tests mit festem „heute"
        jetzt = datetime.combine(heute, jetzt.time())
    aw = auswahl or {}
    fokus = aw.get("fokus", "termine")
    h = hoehe - 1                                   # letzte Zeile: Statusbalken
    if breite >= 86:
        rw = min(40, max(35, (breite - 1) * 2 // 7))
        lbreite = breite - rw - 1
        _a_liste(lw, 0, 0, lbreite, h, daten, ab, heute, erledigte, tage, aw)
        hm = _a_monat(lw, 0, lbreite + 1, rw, daten, ab, heute, erledigte, aw)
        if h - hm >= 5:
            _a_todo(lw, hm, lbreite + 1, rw, h - hm, daten, erledigte, aw)
    else:
        _a_liste(lw, 0, 0, breite, h, daten, ab, heute, erledigte, tage, aw)
    _a_status(lw, hoehe - 1, breite, daten, ab, ende, jetzt, erledigte)
    return lw.zeilen()


def _a_status(lw, y, breite, daten, ab, ende, jetzt, erledigte):
    """Der rote Balken von calcurse über die ganze Breite:
    [ Mi 2026-10-07 | 09:40 ] ── nächster: 18:00 :: Parkour"""
    r = _a_rolle("a_akzent") + INV
    text = "[ %s %s | %s ]" % (WT[jetzt.weekday()], jetzt.date().isoformat(),
                               jetzt.strftime("%H:%M"))
    n = _a_naechster(daten, jetzt.date(), ende, jetzt, erledigte)
    if n:
        d, t = n
        wann = _hm(t["start"]) if d == jetzt.date() else "%s %s" % (WT[d.weekday()], _hm(t["start"]))
        text += " ──> %s :: %s <" % (wann, t["label"])
    text = kuerzen(" " + text, breite)
    lw.setze(y, 0, text + " " * (breite - text_breite(text)), r)


def _a_zyklus(daten, d) -> bool:
    c = daten.get("cycle")
    return isinstance(c, dict) and bool(c.get(d.isoformat()))


def _a_liste(lw, y, x, w, h, daten, ab, heute, erledigte, tage, aw=None):
    """`tage` Tage ab `ab`, jeder Block gleich hoch. Was in einen Block nicht
    passt, wird abgeschnitten — wer mehr sehen will, blättert (←→). Der
    gewählte Termin (aw: tag + idx) steht invertiert, wie bei calcurse."""
    aw = aw or {}
    yy = _paneel(lw, y, x, w, h, "Termine", aktiv=aw.get("fokus", "termine") == "termine")
    sel_tag, sel_idx = aw.get("tag"), aw.get("idx", 0)
    zeigen = aw.get("fokus", "termine") == "termine" and sel_tag is not None
    cx, cw = x + 2, w - 4
    unten = y + h - 1                       # Zeile des unteren Rahmens
    if cw < 8 or unten - yy < 2:
        return
    n = max(1, min(tage, (unten - yy) // 4))
    bh = (unten - yy) // n                  # Zeilen je Tag, inkl. Trennlinie
    for i in range(n):
        d = ab + timedelta(days=i)
        y0 = yy + i * bh
        y_ende = y0 + bh - (1 if i < n - 1 else 0)   # letzte Zeile = Trennlinie
        if d == heute:
            kopf, rk = "heute · %s, %d. %s" % (WT_LANG[d.weekday()], d.day,
                                                 MONATE[d.month - 1]), ROLLE["heute"]
        else:
            kopf, rk = "%s, %d. %s %d" % (WT_LANG[d.weekday()], d.day,
                                           MONATE[d.month - 1], d.year), _a_rolle("a_akzent")
            if _a_zyklus(daten, d):
                rk = ROLLE["zyklus"]
        kopf = kuerzen(kopf, cw)
        lw.setze(y0, cx + cw - text_breite(kopf), kopf, rk)
        zy = y0 + 1
        eintr = _tag_eintraege(daten, d.isoformat(), erledigte)
        hier = zeigen and sel_tag == d.isoformat()
        if not eintr and zy < y_ende:
            lw.setze(zy, cx + 2, "--", ROLLE["leer"] + (INV if hier else ""))
        # Scrollt der gewählte Termin aus dem Block, beginnt der Block später.
        erst = 0
        if hier and eintr:
            platz = max(1, (y_ende - zy + 1) // 3)
            erst = max(0, min(sel_idx, len(eintr) - 1) - platz + 1)
        for k, t in enumerate(eintr):
            if k < erst:
                continue
            zeit = _a_zeit(t)
            if zy + (2 if zeit else 1) > y_ende:
                break
            r = _rolle(t)
            inv = INV if (hier and k == sel_idx) else ""
            if zeit:
                mark = "*" if t["routine"] else "-"
                txt = "%s %s" % (mark, zeit)
                lw.setze(zy, cx + 1, txt + (" " * (cw - 1 - text_breite(txt)) if inv else ""),
                         (r if t["spanne"] else ROLLE["zeit"]) + inv)
                zy += 1
            titel = ("✗ " if t["aus"] else "") + t["label"]
            titel = kuerzen(titel, cw - 3)
            lw.setze(zy, cx + 1 if inv else cx + 3,
                     ("  " + titel + " " * (cw - 3 - text_breite(titel))) if inv else titel,
                     r + inv)
            zy += 2                          # Luft zwischen Terminen, wie calcurse
        if i < n - 1:
            lw.setze(y0 + bh - 1, cx - 1, "─" * (cw + 2), ROLLE["rahmen"])


def _a_monat(lw, y, x, w, daten, ab, heute, erledigte, aw=None) -> int:
    """calcurse-Kalender: Monat mittig, Wochentage und Kalenderwochen in
    Akzentfarbe, heute als [ 7]. Spannen-Tage in Spannenfarbe, Tage mit
    Terminen hell. Liefert die Höhe."""
    erster = (_datum((aw or {}).get("tag")) or ab).replace(day=1)
    letzter = (erster.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    g0 = erster - timedelta(days=erster.weekday())
    wochen = ((letzter - g0).days // 7) + 1
    h = 3 + 2 + wochen + 1
    aw = aw or {}
    yy = _paneel(lw, y, x, w, h, "Kalender", aktiv=aw.get("fokus") == "kalender")
    sel = _datum(aw.get("tag"))
    ak = _a_rolle("a_akzent")
    titel = "%s %d" % (MONATE[erster.month - 1], erster.year)
    lw.setze(yy, x + (w - text_breite(titel)) // 2, titel, ak)
    raster = 4 + 7 * 4                       # KW-Spalte + 7 Tage à 4
    x0 = x + max(1, (w - raster) // 2)
    for c, wt in enumerate(WT):
        lw.setze(yy + 1, x0 + 4 + c * 4 + 1, wt, ak)
    _h, start, ende = _rahmen(daten)
    span_tage = {d for s in _spannen(daten, start, ende, erledigte)
                 for d in _tage(s["von"], s["bis"])}
    for wi in range(wochen):
        mo = g0 + timedelta(days=7 * wi)
        lw.setze(yy + 2 + wi, x0, "%2d" % mo.isocalendar()[1], ak)
        for c in range(7):
            d = mo + timedelta(days=c)
            xx = x0 + 4 + c * 4
            inv = INV if (sel is not None and d == sel) else ""
            if d == heute:
                lw.setze(yy + 2 + wi, xx, "[%2d]" % d.day, ROLLE["heute"] + inv)
                continue
            if d.month != erster.month:
                r = ROLLE["rahmen"]
            elif d in span_tage:
                r = ROLLE["spanne"]
            elif _a_zyklus(daten, d):
                r = ROLLE["zyklus"]
            elif _tag_eintraege(daten, d.isoformat(), erledigte):
                r = ROLLE["termin"]
            else:
                r = ROLLE["routine"]
            lw.setze(yy + 2 + wi, xx + 1, "%2d" % d.day, r + inv)
    return h


def _a_todo(lw, y, x, w, h, daten, erledigte, aw=None):
    """Wo calcurse „TODO" hat: die Wochenliste, die /api/calendar ohnehin
    als `weekplan` mitliefert — nummeriert, erledigte mit „X" statt Nummer
    (wie calcurse). Die gewählte Aufgabe steht invertiert."""
    aw = aw or {}
    an = aw.get("fokus") == "todo"
    yy = _paneel(lw, y, x, w, h, "TODO", aktiv=an)
    cx, cw = x + 2, w - 4
    unten = y + h - 1
    wp = daten.get("weekplan")
    items = wp.get("items") if isinstance(wp, dict) else None
    items = [i for i in (items if isinstance(items, list) else []) if isinstance(i, dict)]
    if not items and yy < unten:
        lw.setze(yy, cx, "nichts zu tun · a legt an" if an else "nichts zu tun",
                 ROLLE["leer"])
    sel = aw.get("tidx", 0)
    erst = max(0, sel - (unten - yy) + 1) if an else 0
    for k, it in enumerate(items):
        if k < erst:
            continue
        if yy >= unten:
            break
        inv = INV if (an and k == sel) else ""
        nr = "X. " if it.get("done") else "%d. " % (k + 1)
        txt = kuerzen(str(it.get("text") or ""), cw - len(nr))
        lw.setze(yy, cx, nr, _a_rolle("a_akzent") + inv)
        lw.setze(yy, cx + len(nr), txt + (" " * (cw - len(nr) - text_breite(txt)) if inv else ""),
                 (ROLLE["aus"] if it.get("done") else ROLLE["routine"]) + inv)
        yy += 1


# ── B: Monatsraster in Kästen (nach calcure) ───────────────────────────
def _monat_grenzen(daten: dict, heute: date, start: date, ende: date) -> tuple:
    erster = _datum(daten.get("first"))
    letzter = _datum(daten.get("last"))
    if not erster or not letzter or letzter < erster:
        ref = _datum(daten.get("ref")) or heute
        if not start <= ref <= ende:
            ref = start + (ende - start) // 2
        erster = ref.replace(day=1)
        letzter = (erster.replace(day=28) + timedelta(days=4)).replace(day=1) \
            - timedelta(days=1)
    return erster, letzter


def _gewaehlt(auswahl) -> tuple:
    """(gewählter Tag, gewählter API-Eintrag) aus der Auswahl der Bedienung.
    Verglichen wird der Eintrag per Identität (t["roh"] is …) — so trifft
    jede Ansicht genau den Termin, den die Bedienung meint, egal wie sie
    ihre Termine anordnet."""
    aw = auswahl or {}
    return _datum(aw.get("tag")), aw.get("roh")


def ansicht_b(daten, breite: int, hoehe: int, erledigte: bool = False,
              auswahl: dict | None = None) -> list:
    """Ganzer Monat als Raster. In den Zellen Anfangszeit + Titel (das „bis"
    steht in A/C — in 14 Zeichen passt es nicht), Ganztägiges als Band,
    jede Spanne als EIN Balken über alle ihre Zellen einer Woche, Rahmen
    inklusive — damit sie nicht als drei einzelne Termine gelesen wird."""
    daten = daten if isinstance(daten, dict) else {}
    cw = (breite - 2) // 7 - 1               # Innenbreite einer Zelle
    if cw < 2 or hoehe < 4:
        return _zu_klein(breite, hoehe)
    lw = Leinwand(breite, hoehe)
    heute, start, ende = _rahmen(daten)
    erster, letzter = _monat_grenzen(daten, heute, start, ende)
    g0 = erster - timedelta(days=erster.weekday())
    wochen = ((letzter - g0).days // 7) + 1
    lw.setze(0, 1, kuerzen("KALENDER · %s %d" % (MONATE[erster.month - 1].upper(),
                                                   erster.year), breite - 1),
             ROLLE["titel"])
    for c, wt in enumerate(WT):
        lw.setze(1, 2 + c * (cw + 1), wt[:cw],
                 ROLLE["wochenende"] if c >= 5 else ROLLE["werktag"])
    r = max(1, (hoehe - 3 - wochen) // wochen)   # Zeilen je Woche inkl. Tageszahl
    rahmen = ROLLE["rahmen"]
    lw.setze(2, 1, "┌" + ("─" * cw + "┬") * 6 + "─" * cw + "┐", rahmen)
    spannen = _spannen(daten, start, ende, erledigte)
    for wi in range(wochen):
        y = 3 + wi * (r + 1)
        mo = g0 + timedelta(days=7 * wi)
        for k in range(r):
            for c in range(8):
                lw.setze(y + k, 1 + c * (cw + 1), "│", rahmen)
        unten = "└┴┘" if wi == wochen - 1 else "├┼┤"
        lw.setze(y + r, 1, unten[0] + ("─" * cw + unten[1]) * 6 + "─" * cw + unten[2],
                 rahmen)
        _b_woche(lw, y, r, cw, mo, erster, letzter, heute, daten, spannen, erledigte,
                 _gewaehlt(auswahl))
    return lw.zeilen()


def _b_woche(lw, y, r, cw, mo, erster, letzter, heute, daten, spannen, erledigte,
             gewaehlt=(None, None)):
    sel_tag, sel = gewaehlt
    sichtbar = [mo + timedelta(days=c) for c in range(7)
                if erster <= mo + timedelta(days=c) <= letzter]
    if not sichtbar:
        return
    w0, w1 = sichtbar[0], sichtbar[-1]
    # Spannen dieser Woche auf Bahnen verteilen: was sich nicht überschneidet,
    # teilt sich eine Zeile (wie die Spann-Gosse im alten Kalender).
    bahnen_ende: list = []
    belegt = []
    for sp in spannen:
        a, b = max(sp["von"], w0), min(sp["bis"], w1)
        if a > b:
            continue
        for bi, e in enumerate(bahnen_ende):
            if a > e:
                bahnen_ende[bi] = b
                break
        else:
            bi = len(bahnen_ende)
            bahnen_ende.append(b)
        belegt.append((bi, a, b, sp))
    platz = r - 1                            # Zeilen unter der Tageszahl
    versteckt = {d: 0 for d in sichtbar}
    for bi, a, b, sp in belegt:
        if bi >= platz:
            for d in _tage(a, b):
                versteckt[d] += 1
            continue
        x0 = 2 + a.weekday() * (cw + 1)
        breite = (b.weekday() - a.weekday() + 1) * (cw + 1) - 1
        ist = sel is not None and any(t["roh"] is sel for t in sp["tage"].values())
        lw.setze(y + 1 + bi, x0, _balken_text(sp, a, b, breite),
                 (_a_rolle("a_akzent") if ist else ROLLE["spanne"]) + INV)
    nb = min(len(bahnen_ende), platz)
    for d in sichtbar:
        x0 = 2 + d.weekday() * (cw + 1)
        if d == sel_tag:                     # gewählter Tag: Zahl in Akzentfläche
            lw.setze(y, x0, kuerzen((" %d " if d == heute else "%d ") % d.day, cw),
                     _a_rolle("a_akzent") + INV)
        elif d == heute:
            lw.setze(y, x0, kuerzen(" %d " % d.day, cw), ROLLE["heute"] + INV)
        else:
            lw.setze(y, x0, kuerzen("%d" % d.day, cw),
                     ROLLE["wochenende"] if d.weekday() >= 5 else ROLLE["termin"])
        rest = [t for t in _tag_eintraege(daten, d.isoformat(), erledigte)
                if not t["spanne"]]
        frei = platz - nb
        zeige = rest if len(rest) + versteckt[d] <= frei else rest[:max(0, frei - 1)]
        # Ist der gewählte Termin weggekürzt, nimmt er den letzten Platz ein.
        if d == sel_tag and sel is not None and zeige and \
                not any(t["roh"] is sel for t in zeige):
            gew = [t for t in rest if t["roh"] is sel]
            if gew:
                zeige = zeige[:-1] + gew
        for k, t in enumerate(zeige):
            yy = y + 1 + nb + k
            if d == sel_tag and sel is not None and t["roh"] is sel:
                txt = ((_hm(t["start"]) + " ") if t["start"] is not None and cw >= 9 else "") + t["label"]
                txt = kuerzen(txt, cw)
                lw.setze(yy, x0, txt + " " * (cw - text_breite(txt)), _a_rolle("a_akzent") + INV)
                continue
            if t["start"] is None and t["ende"] is None:
                # Ganztägig als Band: Fläche über die ganze Zellenbreite.
                band = kuerzen(t["label"], cw)
                band += " " * (cw - text_breite(band))
                lw.setze(yy, x0, band, _rolle(t) + ("" if t["aus"] else INV))
            else:
                # Unter 9 Spalten wäre „10:…" alles, was übrig bleibt — dann
                # lieber den Titel; die Uhrzeit zeigen A und C.
                zeit = _hm(t["start"]) + " " if t["start"] is not None and cw >= 9 else ""
                lw.setze(yy, x0, kuerzen(zeit + t["label"], cw), _rolle(t))
        mehr = len(rest) - len(zeige) + versteckt[d]
        if mehr and frei > 0:
            lw.setze(y + 1 + nb + len(zeige), x0, kuerzen("+%d" % mehr, cw), ROLLE["leer"])


def _balken_text(sp: dict, a: date, b: date, n: int) -> str:
    """Beschriftung eines Spannen-Balkens auf n Spalten, z. B.
    „ Fr 18:00 ━━ Wochenende Berlin ━━ So 14:00 ". Läuft die Spanne über
    die Woche hinaus, zeigt ◀/▶ das an. Wird es eng, fällt zuerst der
    Schmuck weg, dann die Ränder, zuletzt wird der Titel gekürzt."""
    t0, t1 = sp["tage"].get(sp["von"]), sp["tage"].get(sp["bis"])
    if sp["von"] < a:
        links = "◀"
    else:
        s = t0["start"] if t0 else None
        links = WT[a.weekday()] + (" " + _hm(s) if s is not None else "")
    if sp["bis"] > b:
        rechts = "▶"
    else:
        e = t1["ende"] if t1 else None
        rechts = WT[b.weekday()] + (" " + _hm(e) if e is not None else "")
    titel = sp["label"]
    for kand in (" %s ━━ %s ━━ %s " % (links, titel, rechts),
                 " %s %s %s " % (links, titel, rechts)):
        if text_breite(kand) <= n:
            return kand + " " * (n - text_breite(kand))
    # Von und bis sind wichtiger als der volle Titel: erst den Titel kürzen.
    rest = n - text_breite(" %s  %s " % (links, rechts))
    if rest >= 4:
        kand = " %s %s %s " % (links, kuerzen(titel, rest), rechts)
        return kand + " " * (n - text_breite(kand))
    t = kuerzen(" " + titel, n)
    return t + " " * (n - text_breite(t))


# ── C: Woche als Zeitachse ─────────────────────────────────────────────
_SCHRITTE = (10, 15, 20, 30, 40, 60, 90, 120, 180, 240, 360)
_STANDARD_DAUER = 60      # Termin ohne Ende: eine Stunde Fläche


def _c_bloecke(daten, tag: date, erledigte):
    """Zeit-Blöcke eines Tages: [(start, ende, eintrag)] und die
    Ganztags-Einträge ohne Spanne (die gehören nicht auf die Achse)."""
    bloecke, ganz = [], []
    for t in _tag_eintraege(daten, tag.isoformat(), erledigte):
        s, e = t["start"], t["ende"]
        if t["spanne"]:
            # Spannentage ohne Uhrzeit füllen den ganzen Tag — so wird die
            # Spanne zur durchgehenden Fläche über alle ihre Tage.
            s = 0 if s is None else s
            e = 24 * 60 if e is None else e
        elif s is None:
            if e is None:
                ganz.append(t)
                continue
            s = max(0, e - _STANDARD_DAUER)
        elif e is None:
            e = min(24 * 60, s + _STANDARD_DAUER)
        bloecke.append((s, e, t))
    return bloecke, ganz


def _c_bahnen(bloecke):
    """Überschneidungen nebeneinander: jeder Block bekommt eine Bahn,
    die erste freie (Greedy, wie im Handy-Kalender)."""
    ende_je_bahn: list = []
    out = []
    for s, e, t in sorted(bloecke, key=lambda b: (b[0], -b[1])):
        for i, be in enumerate(ende_je_bahn):
            if s >= be:
                ende_je_bahn[i] = e
                break
        else:
            i = len(ende_je_bahn)
            ende_je_bahn.append(e)
        out.append((i, s, e, t))
    return out, max(1, len(ende_je_bahn))


def _c_label(t: dict, s: int, e: int, bw: int) -> str:
    if t["spanne"]:
        if t["start"] is not None and t["ende"] is not None:
            vb = "%s–%s" % (_hm_kurz(s), _hm_kurz(e))
        elif t["start"] is not None:
            vb = "%s→" % _hm_kurz(s)
        elif t["ende"] is not None:
            vb = "→%s" % _hm_kurz(e)
        else:
            vb = "↔"
    elif t["ende"] is not None and t["start"] is not None:
        vb = "%s–%s" % (_hm_kurz(s), _hm_kurz(e))
    else:
        vb = _hm_kurz(s if t["start"] is not None else e)
    voll = vb + " " + t["label"]
    if text_breite(voll) <= bw:
        return voll
    # Schmale Säule: die Uhrzeit steht ohnehin an der Achse, die Fläche zeigt
    # die Dauer — der Titel hat Vorrang. Spannen behalten ihren Pfeil, der
    # sagt, dass es am Nachbartag weitergeht.
    if bw < 5:
        return kuerzen(t["label"], bw)      # ein Pfeil vor „…" sagt nichts
    # Kurze Spannen-Marken („18→", „→14", „↔") bleiben: sie sagen, wann es
    # anfängt/aufhört und dass es am Nachbartag weitergeht.
    if t["spanne"] and text_breite(vb) <= 4:
        return kuerzen(vb + " " + t["label"], bw)
    return kuerzen(t["label"], bw)


def ansicht_c(daten, breite: int, hoehe: int, erledigte: bool = False,
              auswahl: dict | None = None) -> list:
    """Eine Woche, Stunden nach unten, Tage nebeneinander. Termine sind
    Flächen so lang wie ihre Dauer; ein Spannentag ohne Uhrzeit ist eine
    volle Säule, so läuft die Spanne als Fläche über ihre Tage."""
    daten = daten if isinstance(daten, dict) else {}
    sel_tag, sel = _gewaehlt(auswahl)
    innen = breite - 2
    g = 7 if innen >= 7 + 7 * 8 else (6 if innen >= 6 + 7 * 4 else 3)
    colw = (innen - g) // 7
    if colw < 2 or hoehe < 5:
        return _zu_klein(breite, hoehe)
    lw = Leinwand(breite, hoehe)
    heute, start, ende = _rahmen(daten)
    ref = _datum(daten.get("ref")) or heute
    if not start <= ref <= ende:
        ref = start
    mo = ref - timedelta(days=ref.weekday())
    woche = [mo + timedelta(days=i) for i in range(7)]
    so = woche[-1]
    kw = mo.isocalendar()[1]
    if mo.month == so.month:
        span = "%s–%s %s" % (mo.strftime("%d."), so.strftime("%d."), MONATE[mo.month - 1])
    else:
        span = "%s–%s" % (mo.strftime("%d.%m."), so.strftime("%d.%m."))
    _kasten(lw, 0, 0, breite, hoehe, "woche %d · %s" % (kw, span))

    tage = [_c_bloecke(daten, d, erledigte) for d in woche]
    x0 = 1 + g
    for i, d in enumerate(woche):
        r = ROLLE["heute"] if d == heute else (
            ROLLE["c_wochenende"] if d.weekday() >= 5 else ROLLE["titel"])
        kopf = "%s %s" % (WT[d.weekday()], d.strftime("%d."))
        kopf = kopf if len(kopf) < colw else WT[d.weekday()][:colw - 1]
        if d == sel_tag:                     # gewählter Tag: Kopf in Akzentfläche
            r, kopf = _a_rolle("a_akzent") + INV, kopf + " " * (colw - 1 - text_breite(kopf))
        lw.setze(1, x0 + i * colw, kopf, r)
    y0 = 2
    if any(ganz for _b, ganz in tage):
        lw.setze(y0, 1, kuerzen("ganzt.", g - 1), ROLLE["zeit"])
        for i, (_b, ganz) in enumerate(tage):
            if ganz:
                t = ganz[0]
                txt = t["label"] + (" +%d" % (len(ganz) - 1) if len(ganz) > 1 else "")
                band = kuerzen(txt, colw - 1)
                rolle = _rolle(t) + ("" if t["aus"] else INV)
                if sel is not None and any(x["roh"] is sel for x in ganz):
                    t = next(x for x in ganz if x["roh"] is sel)
                    band = kuerzen(t["label"], colw - 1)
                    rolle = _a_rolle("a_akzent") + INV
                lw.setze(y0, x0 + i * colw, band + " " * (colw - 1 - text_breite(band)), rolle)
        y0 += 1
    _c_achse(lw, y0, hoehe - 1, x0, g, colw, tage, breite, sel)
    return lw.zeilen()


def _c_achse(lw, y0, y_ende, x0, g, colw, tage, breite, sel=None):
    """Zeitachse von y0 bis vor y_ende. Das Fenster ist FEST 08–22 Uhr
    (Sasha, 08.10.2026: nicht für einen Nachttermin die ganze Woche
    aufziehen); der Zeilen-Takt ist der feinste, mit dem es in die Höhe
    passt. Was ganz außerhalb liegt, zeigt der Tag mit ▲ (früher) bzw.
    ▼ (später). Wird so ein Termin gewählt, rollt das Fenster zu ihm —
    für die ganze Woche, damit die Uhrzeiten links für alle Tage stimmen."""
    reihen = y_ende - y0
    if reihen < 1:
        return
    basis_lo, basis_hi = 8 * 60, 22 * 60
    for m in _SCHRITTE:
        # Beschriftung lab muss ein Vielfaches des Takts sein und der Anfang
        # auf ihr liegen — sonst trifft keine Zeile eine beschriftete Stunde
        # und Uhrzeiten wie Punktlinien fehlen ganz.
        lab = next(x for x in (60, 120, 180, 240, 360, 720, 1440) if x >= 2 * m and x % m == 0)
        if math.ceil((basis_hi - basis_lo) / m) <= reihen:
            break
    sicht = reihen * m
    lo = basis_lo
    if sel is not None:                      # gewählter Termin ganz draußen → hinrollen
        for bloecke, _g in tage:
            for s0, e0, t in bloecke:
                if t["roh"] is not sel:
                    continue
                if e0 <= lo:
                    lo = s0 - s0 % lab
                elif s0 >= lo + sicht:
                    lo = max(s0 - s0 % lab, -(-(e0 - sicht) // lab) * lab)
    lo = max(0, min(lo, 24 * 60 - sicht))
    lo -= lo % lab
    n = min(reihen, max(1, math.ceil((24 * 60 - lo) / m)))
    sicht_ende = lo + n * m
    farbe: dict = {}
    for k in range(n):
        t = lo + k * m
        if t % lab == 0:
            lw.setze(y0 + k, 1, kuerzen(_hm(t) if g >= 6 else "%02d" % (t // 60), g - 1),
                     ROLLE["rahmen"])
            lw.setze(y0 + k, x0, "·" * (7 * colw), ROLLE["rahmen"])
    for i, (bloecke, _g) in enumerate(tage):
        bahnen, nb = _c_bahnen(bloecke)
        pw = colw - 1
        teil = max(1, (pw - (nb - 1)) // nb)
        for bi, s, e, t in bahnen:
            if e <= lo or s >= sicht_ende:
                continue
            bx = x0 + i * colw + bi * (teil + 1)
            bw = teil if bi < nb - 1 else max(1, pw - bi * (teil + 1))
            if bx >= x0 + i * colw + pw:
                continue
            k0 = (max(s, lo) - lo) // m
            k1 = max(k0, math.ceil((min(e, sicht_ende) - lo) / m) - 1)
            if t["spanne"]:
                r = farbe.setdefault(t["key"], SPANNEN_FARBEN[len(farbe) % len(SPANNEN_FARBEN)])
            else:
                r = ROLLE["block_routine"] if t["routine"] else ROLLE["block_termin"]
            if t["aus"]:
                r = ROLLE["aus"]
            if sel is not None and t["roh"] is sel:   # gewählter Termin: Akzent
                r = _a_rolle("a_akzent")
            lab_txt = _c_label(t, s, e, bw)
            lw.setze(y0 + k0, bx, lab_txt + " " * (bw - text_breite(lab_txt)), r + INV)
            for k in range(k0 + 1, k1 + 1):
                lw.setze(y0 + k, bx, ("░" if t["aus"] else "█") * bw, r)
        # Ganz außerhalb des Fensters? Dann ein Pfeil in der Spalte des Tages.
        rechts = x0 + i * colw + max(0, colw - 2)
        if any(e <= lo for _bi, s, e, _t in bahnen):
            lw.setze(y0, rechts, "▲", _a_rolle("a_akzent"))
        if any(s >= sicht_ende for _bi, s, e, _t in bahnen):
            lw.setze(y0 + n - 1, rechts, "▼", _a_rolle("a_akzent"))
