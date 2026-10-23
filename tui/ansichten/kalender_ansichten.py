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
import re
import unicodedata
import zlib
from datetime import date, timedelta

from . import kalender_deadline, kalender_ebenen, kalender_gruppen, kalender_jetzt, kalender_motive, kalender_stil

# ── Ansichten und Taste v ──────────────────────────────────────────────
ANSICHTEN = ("A", "B", "C")
ANSICHT_NAMEN = {"A": "tagesliste", "B": "monat", "C": "woche"}
# Welche /api/calendar-Form jede Ansicht braucht. A will „ab heute" mehr als
# eine Woche zeigen und einen ganzen Mini-Monat färben → Monatsdaten.
DATENANSICHT = {"A": "month", "B": "month", "C": "week"}
# Wie weit ←→ springt. A zeigt nur ein paar Tage ab `ref` → tageweise.
SCHRITT = {"A": "tag", "B": "monat", "C": "woche"}

INV = "_inv"
# Gedämpfte Schrift AUF einer Fläche (Rolle „k_t3_inv_leise"): Liste unter dem
# Titel, Zeit im Block. kalender.py mischt die Schrift zum Grund hin.
LEISE = "_leise"

# Semantik → Palettenrolle. Seit 09.10.2026 zeigen alle drei Ansichten auf
# EINE Kalender-Tabelle (tui/ansichten/farben.py, KAL → C["k_…"]): gleiche
# Art = gleiche Farbe, egal ob Liste, Monat oder Woche. Nur Rahmen, Zeiten
# und Leeres bleiben in den Grautönen der übrigen TUI.
ROLLE = {
    "rahmen": "faint",          # Kastenlinien, Trenner, Punkt-Raster
    "titel": "k_akzent",        # Kastentitel, Tagesköpfe, Monatskopf
    "heute": "k_heute",         # heutiger Tag
    "zeit": "faint",            # „10:00–18:00" in der Liste
    # Termine, Routinen, Ganztägiges: Farbe nach Titel (titel_rolle unten);
    # diese drei sind nur noch der Rückfall, wenn ein Titel fehlt.
    "routine": "k_t0",
    "termin": "k_t0",
    "ganztags": "k_t0",
    "spanne": "k_sp1",          # mehrtägig (erste Farbe der Reihe)
    "werktag": "dim",           # Mo–Fr-Köpfe im Raster
    "tag_belegt": "bright",     # Mini-Monat: Tag mit Einträgen
    "tag_frei": "dim",          # Mini-Monat: Tag ohne
    "wochenende": "k_wochenende",   # Sa/So-Köpfe, in B und C gleich
    "leer": "faint",            # „—" an leeren Tagen, „+2" bei Überlauf
    "aus": "faint",             # deaktiviert / Ausfall (nur mit erledigte=True)
    "c_wochenende": "k_wochenende",
    "a_akzent": "k_akzent",     # Titel, Datum, KW, Auswahl, Statuszeile — alle Ansichten
    "a_aktiv": "k_akzent",      # Rahmen des aktiven Kastens
    "zyklus": "cyc",            # Zyklus-Tönung (aus dem »periode«-Graphen)
    "sync_warn": "warn",        # „⚠ google-sync: Zugang abgelaufen — seit …"
}
# Stand des Google-Syncs (16.10.2026, daten["sync"] aus /api/calendar):
# mit Problem eine Warnung in der Statuszeile von A und im Kopf von B/C;
# ohne Problem höchstens leise „google ✓ 16:31" in der Statuszeile von A.
# Sasha entscheidet: False → ohne Problem steht gar nichts da.
SYNC_OK_ZEIGEN = True
# Nebeneinanderliegende Spannen müssen unterscheidbar sein → reihum vergeben.
SPANNEN_FARBEN = ("k_sp1", "k_sp2", "k_sp3", "k_sp4")
TITEL_FARBEN = tuple("k_t%d" % i for i in range(12))

# ── Farbe je Kurs ──────────────────────────────────────────────────────
# Sasha, 10.10.2026: „manche kurse heißen leicht anderes, sind aber
# dieselben. exphy = experimentalphysik … ich habe nur 4 kurse". Darum zählt
# nur das ERSTE Wort des Titels („Analysis Saalübung" = „Analysis I",
# „Theoretische Physik Ia Tutorium" = „Theoretische Physik Ia"), und
# Kurzformen werden auf den vollen Namen gelegt. Neue Kurzform → hier rein.
KURZFORMEN = {
    "exphy": "experimentalphysik",
    "tp": "theoretische",       # „TP Sprechstunde …" (23.10.2026)
    "ana": "analysis",          # „Ana Tutorium …", „Ana Sprechstunde …"
}
# Wiederkehrendes bekommt beim ersten Auftauchen fest eine FREIE Farbe
# (farben_vergeben); die Tabelle hält tui/ansichten/kalender.py auf Platte,
# damit eine Farbe nie wandert. Einmaliges nimmt seine Rechen-Farbe (crc32)
# und belegt keinen Platz.
FARBTABELLE: dict = {}
# Vergabe-Reihenfolge der Plätze in farben.KAL (t0…t11): die ersten fünf so
# verschieden wie möglich (Cyan, Orange, Pink, Meergrün, Violett), damit die
# häufigsten Kurse sich nie ähneln; danach der Rest.
RANGFOLGE = (0, 3, 1, 11, 2, 8, 5, 4, 9, 6, 10, 7)


def titel_schluessel(label) -> str:
    """Der Kurs hinter einem Titel: erstes Wort, ohne Ort, klein.

    Bewusst eine KOPIE von core/kalender_kategorie.titel_schluessel (10.10.2026):
    die TUI läuft auch auf dem Aussenposten ohne Kern, und kalender_kategorie
    hängt an kalender_fehler — kein „reiner Helfer" für die Tür `tui/` in
    memory/system/bauplan_kern.md. tests/test_kalender_gruppen_tui.py prüft,
    dass beide gleich rechnen (auch KURZFORMEN)."""
    name = (label or "").split(" @ ")[0].strip().lower()
    wort = re.split(r"[\s\-–:/,.()]+", name)[0] if name else ""
    return KURZFORMEN.get(wort, wort)


def _rechenplatz(schluessel: str) -> int:
    # crc32, nicht hash(): der ist je Prozess anders
    return zlib.crc32(schluessel.encode("utf-8")) % len(TITEL_FARBEN)


def gruppe_rolle(roh) -> str:
    """Feste Farbe einer Gruppe (B): Schlüssel „gruppe:uni" in derselben
    FARBTABELLE wie die Kurse (farben_vergeben)."""
    k = kalender_gruppen.farb_schluessel(roh)
    if not k:
        return ROLLE["termin"]
    platz = FARBTABELLE.get(k)
    if not isinstance(platz, int) or not 0 <= platz < len(TITEL_FARBEN):
        platz = _rechenplatz(k)
    return TITEL_FARBEN[platz]


def titel_rolle(label) -> str:
    k = titel_schluessel(label)
    if not k:
        return ROLLE["termin"]
    platz = FARBTABELLE.get(k)
    if not isinstance(platz, int) or not 0 <= platz < len(TITEL_FARBEN):
        platz = _rechenplatz(k)
    return TITEL_FARBEN[platz]


def kurs_rolle(t: dict) -> str:
    """Farbe eines normierten Eintrags: Quellen-Termin fest nach der Quelle
    („quelle:<id>" in derselben FARBTABELLE), sonst nach dem Kurs im Titel.
    Eine erledigte Liste („leer") ist gedämpft."""
    q = t.get("quelle")
    if not q:
        return titel_rolle(t.get("label"))
    if q["zustand"] == "leer":
        return ROLLE["leer"]
    platz = FARBTABELLE.get(q["schl"])
    if not isinstance(platz, int) or not 0 <= platz < len(TITEL_FARBEN):
        platz = _rechenplatz(q["schl"])
    return TITEL_FARBEN[platz]


def farben_vergeben(daten: dict, tabelle: dict) -> bool:
    """Jeder Kurs, der in `daten` mindestens zweimal vorkommt und noch keine
    Farbe hat, bekommt die nächste freie in RANGFOLGE. Häufigere zuerst,
    damit die echten Kurse die deutlichsten Farben haben. Ändert
    `tabelle`; True, wenn etwas dazukam (dann speichern). Gruppen zählen
    als „gruppe:<schlüssel>" mit (eigene Farbe in B), Phasen des
    Tagesrhythmus gar nicht (sie sind Hintergrund, kein Kurs)."""
    zahl: dict = {}
    tage = daten.get("days") if isinstance(daten, dict) else None
    for liste in (tage.values() if isinstance(tage, dict) else []):
        for e in liste if isinstance(liste, list) else []:
            if isinstance(e, dict) and not (e.get("span") or e.get("von")) \
                    and not kalender_motive.ist_phase(e):
                q = quelle_info(e)
                kurs = q["schl"] if q else titel_schluessel(e.get("label"))
                for k in (kurs, kalender_gruppen.farb_schluessel(e)):
                    if k:
                        zahl[k] = zahl.get(k, 0) + 1
    neu = sorted((k for k, n in zahl.items() if n >= 2 and k not in tabelle),
                 key=lambda k: (-zahl[k], k))
    for k in neu:
        belegt = set(tabelle.values())
        frei = [p for p in RANGFOLGE if p not in belegt]
        tabelle[k] = frei[0] if frei else _rechenplatz(k)
    return bool(neu)

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

    def glas(self, y: int, x: int, breite: int, glasrolle: str,
             text: str = "", schrift: str | None = None) -> None:
        """Glasscheibe über `breite` Zellen ab x (Ebene „uncommitted"): was
        schon dasteht — Punktlinien, Flächen und Schrift fester Termine —
        bleibt stehen, nur sein Hintergrund wird mit der Farbe von
        `glasrolle` gemischt (Rolle „<darunter>~<glas>", kalender.py löst sie
        auf). `text` (das Label des Eintrags) wird ab x darübergesetzt,
        ebenfalls auf gemischtem Grund: „<darunter>~<glas>~<schrift>".

        Sasha, 10.10.2026: „es sieht nicht transparent aus da der hintergrund
        nicht durchscheint" — darum keine eigene Fläche mehr, sondern Glas."""
        if not 0 <= y < self.h:
            return
        reihe = self.z[y]
        unter = [r.split(GLAS)[0] for _ch, r in reihe]
        for cx in range(max(0, x), min(self.b, x + breite)):
            reihe[cx] = (reihe[cx][0], unter[cx] + GLAS + glasrolle)
        if text:
            ende = self.setze(y, x, text, glasrolle)
            for cx in range(max(0, x), min(self.b, ende)):
                reihe[cx] = (reihe[cx][0], unter[cx] + GLAS + glasrolle + GLAS
                             + (schrift or glasrolle))


# Trenner der Glas-Rollen (Leinwand.glas): „faint~k_t3" = Punkt auf Glas
GLAS = "~"


def glas_teile(rolle: str) -> tuple:
    """„unter~glas[~schrift]" → (unter, glas, schrift|None); keine Glas-Rolle
    → (rolle, None, None)."""
    t = rolle.split(GLAS)
    if len(t) < 2:
        return rolle, None, None
    return t[0], t[1], (t[2] if len(t) > 2 else None)


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


def sync_hinweis(daten) -> tuple:
    """(warnung, leise) aus daten["sync"] — je ein Text oder None."""
    s = daten.get("sync") if isinstance(daten, dict) else None
    if not isinstance(s, dict):
        return None, None
    if s.get("problem") and s.get("hinweis"):
        return s["hinweis"], None
    return None, (s.get("kurz") if SYNC_OK_ZEIGEN else None)


def _sync_kopf(lw, y, links: int, rechts: int, daten) -> None:
    """Die Sync-Warnung rechtsbündig in eine Kopfzeile (B, C), endet vor
    Spalte `rechts`, beginnt nie vor `links`."""
    warnung, _leise = sync_hinweis(daten)
    if not warnung:
        return
    text = kuerzen(" %s " % warnung, rechts - links)
    if text_breite(text) >= 8:
        lw.setze(y, rechts - text_breite(text), text, ROLLE["sync_warn"])


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


def quelle_info(e: dict) -> dict | None:
    """Termin mit Titel aus Liste/Projekt (core/kalender_quelle.py, „quelle")
    → {"name", "zustand", "schl"} — sonst None. Sasha, 10.10.2026: „im
    container steht das dann als ‚titel' wie ein normaler termin titel und
    unten drunter weniger stark sichtbar dezent ‚titel der liste'"."""
    q = e.get("quelle")
    if not isinstance(q, dict) or not q.get("id"):
        return None
    return {"name": str(e.get("quelle_name") or e.get("label") or "?"),
            "zustand": e.get("quelle_zustand") or "ok",
            # Farbe fest nach der Quelle, nicht nach dem Titel: sonst wechselte
            # der Block bei jedem Abhaken die Farbe.
            "schl": "quelle:%s" % q["id"]}


def quelle_unterzeile(t: dict) -> str | None:
    """Die dezente Zeile unter dem Titel: Name der Liste; „leer" braucht
    keine (der Titel sagt schon „— alles erledigt"), „fehlt" einen Hinweis."""
    q = t.get("quelle")
    if not q or q["zustand"] == "leer":
        return None
    if q["zustand"] == "fehlt":
        return "liste fehlt"
    return q["name"]


def _normiere(e: dict, iso: str, aus: bool) -> dict:
    gespeichert = str(e.get("label") or "?")
    quelle = quelle_info(e)
    # Quellen-Termin: der Titel ist live der oberste offene Punkt (titel_live);
    # `label` bleibt der Rückfall und der Schlüssel für die Werkzeuge (roh).
    label = str(e.get("titel_live") or gespeichert) if quelle else gespeichert
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
    # Deadline (20.10.2026): ein Zeitpunkt — ein Ende (vom Server dazugegeben)
    # zählt nicht; ohne Uhrzeit ist es keine (dann wie ein normaler Termin).
    deadline = kalender_deadline.ist(e) and s is not None and not spanne
    if deadline:
        en = None
    return {
        "label": label, "start": s, "ende": en, "spanne": spanne,
        "erster": erster, "letzter": letzter, "tag": iso,
        "von": e.get("von") if isinstance(e.get("von"), str) else iso,
        "bis": e.get("bis") if isinstance(e.get("bis"), str) else iso,
        "key": (e.get("von"), e.get("bis"), gespeichert, e.get("layer")),
        "quelle": quelle,
        # Aussehen des Kastens aus der Stylebox (kalender_stil.py); {} = wie immer
        "stil": kalender_stil.von(e),
        "routine": bool(e.get("recurring")), "aus": aus,
        # Ebene „uncommitted": blass; in C UNTER den festen (22.10.2026)
        "unv": e.get("layer") == UNVERBINDLICH,
        "ausfall": bool(e.get("ausfall")),
        "deadline": deadline,
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
        # Phasen des Tagesrhythmus sind kein Termin (10.10.2026): nicht wählbar,
        # keine Zeile, kein Block — C malt sie als Hintergrund (kalender_motive).
        if kalender_motive.ist_phase(e):
            continue
        aus = bool(e.get("deaktiviert") or e.get("ausfall"))
        if aus and not erledigte:
            continue
        t = _normiere(e, iso, aus)
        if t["deadline"] and not kalender_deadline.zeigen(t):
            continue                   # überschritten, und Sasha will sie nicht sehen
        out.append(t)
    # Spannen zuerst (sie rahmen den Tag), dann Ganztägiges, dann nach Zeit.
    out.sort(key=lambda t: (not t["spanne"], t["start"] is not None,
                            t["start"] if t["start"] is not None else 0))
    return out


def monat_eintraege(daten: dict, iso: str, erledigte: bool) -> list:
    """Die Liste eines Tages in B: wie _tag_eintraege, nur gleiche Gruppen
    als EINE Zeile (kalender_gruppen.zusammenfassen). Die Bedienung wählt in
    B aus genau dieser Liste."""
    return kalender_gruppen.zusammenfassen(_tag_eintraege(daten, iso, erledigte))


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


UNVERBINDLICH = "uncommitted"


def blass(rolle: str, t: dict) -> str:
    """Kalenderfarbe → ihre blasse Schrift, wenn `t` uncommitted ist
    (C["k_…_blass"]; tui/ansichten/kontext.py). Nur noch für Zeilen, unter
    denen nichts liegt (A, Textzeilen in B, das Verdeckt-Zeichen in C). Flächen
    (B, C) zeichnet Leinwand.glas — in C nur über Punktlinien/Phasen, nie über
    festen Terminen."""
    return rolle + "_blass" if t.get("unv") and rolle.startswith("k_") else rolle


def _rolle(t: dict) -> str:
    if t["aus"]:
        return ROLLE["aus"]
    if t["spanne"]:
        return blass(ROLLE["spanne"], t)
    if t.get("gruppe"):
        return blass(gruppe_rolle(t["roh"]), t)
    return blass(kurs_rolle(t), t)


def _glasrolle(t: dict) -> str:
    """Die Farbe, in der ein uncommitted-Eintrag als Glas liegt."""
    if t.get("gruppe"):
        return gruppe_rolle(t["roh"])
    return ROLLE["spanne"] if t["spanne"] else kurs_rolle(t)


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
    jetzt = uhr_jetzt = jetzt or kalender_jetzt.jetzt()   # ► steht beim echten Jetzt, wie in C
    if jetzt.date() != heute:          # Vorschau/Tests mit festem „heute"
        jetzt = datetime.combine(heute, jetzt.time())
    aw = auswahl or {}
    fokus = aw.get("fokus", "termine")
    h = hoehe - 1                                   # letzte Zeile: Statusbalken
    if breite >= 86:
        rw = min(40, max(35, (breite - 1) * 2 // 7))
        lbreite = breite - rw - 1
        _a_liste(lw, 0, 0, lbreite, h, daten, ab, heute, erledigte, tage, aw, uhr_jetzt)
        hm = _a_monat(lw, 0, lbreite + 1, rw, daten, ab, heute, erledigte, aw)
        if h - hm >= 5:
            _a_todo(lw, hm, lbreite + 1, rw, h - hm, daten, erledigte, aw)
    else:
        _a_liste(lw, 0, 0, breite, h, daten, ab, heute, erledigte, tage, aw, uhr_jetzt)
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
    # rechts im Balken: Stand des Google-Syncs (Warnung in Warnfarbe, sonst leise)
    warnung, leise = sync_hinweis(daten)
    zusatz = warnung or leise
    if zusatz:
        # die Warnung geht vor: sie darf den „nächsten Termin“ bis auf ein Drittel kürzen
        platz = breite - min(text_breite(text), breite // (3 if warnung else 2)) - 2
        zusatz = kuerzen(" " + zusatz + " ", platz)
        if text_breite(zusatz) >= 6:
            lw.setze(y, breite - text_breite(zusatz), zusatz,
                     ROLLE["sync_warn"] + INV if warnung else r)


def _a_zyklus(daten, d) -> bool:
    c = daten.get("cycle")
    return isinstance(c, dict) and bool(c.get(d.isoformat()))


def _a_liste(lw, y, x, w, h, daten, ab, heute, erledigte, tage, aw=None, jetzt=None):
    """`tage` Tage ab `ab`, jeder Block gleich hoch. Was in einen Block nicht
    passt, wird abgeschnitten — wer mehr sehen will, blättert (←→). Der
    gewählte Termin (aw: tag + idx) steht invertiert, wie bei calcurse; vor
    dem laufenden bzw. nächsten von heute steht ein goldener ► (kalender_jetzt)."""
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
        _a_phasen(lw, y0, cx, cw - text_breite(kopf) - 2, daten, d)
        zy = y0 + 1
        eintr = _tag_eintraege(daten, d.isoformat(), erledigte)
        hier = zeigen and sel_tag == d.isoformat()
        ziel = (kalender_jetzt.a_ziel(eintr, jetzt)
                if jetzt is not None and d == jetzt.date() else None)
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
            if t["deadline"]:                # eine Zeile, Leucht-Rot (kalender_deadline)
                if zy + 1 > y_ende:
                    break
                _a_deadline(lw, zy, cx, cw, t, hier and k == sel_idx)
                zy += 2
                continue
            zeit = _a_zeit(t)
            if zy + (2 if zeit else 1) > y_ende:
                break
            if t is ziel:
                lw.setze(zy, cx, kalender_jetzt.PFEIL, kalender_jetzt.ROLLE)
            inv = INV if (hier and k == sel_idx) else ""
            r = ROLLE["a_akzent"] if inv else _rolle(t)     # Auswahl: Akzentfläche wie in B/C
            if zeit:
                mark = "*" if t["routine"] else "-"
                txt = "%s %s" % (mark, zeit)
                lw.setze(zy, cx + 1, txt + (" " * (cw - 1 - text_breite(txt)) if inv else ""),
                         (r if (t["spanne"] or inv) else ROLLE["zeit"]) + inv)
                zy += 1
            titel = ("✗ " if t["aus"] else "") + t["label"]
            titel = kuerzen(titel, cw - 3)
            if t["stil"] and not inv and not t["aus"]:      # Stylebox: Rahmenzeichen + Farbe
                kalender_stil.a_titel(lw, zy, cx + 3, cw - 3, titel, r, t["stil"])
            else:
                lw.setze(zy, cx + 1 if inv else cx + 3,
                         ("  " + titel + " " * (cw - 3 - text_breite(titel))) if inv else titel,
                         r + inv)
            # Quellen-Termin: darunter dezent die Liste (eine Zeile mehr, die
            # Luft zum nächsten Termin bleibt — calcurse-Takt bleibt erkennbar).
            unter = quelle_unterzeile(t)
            if unter and zy + 1 < y_ende:
                zy += 1
                unter = kuerzen(unter, cw - 3)
                if inv:
                    lw.setze(zy, cx + 1, "  " + unter + " " * (cw - 3 - text_breite(unter)),
                             r + INV + LEISE)
                else:
                    lw.setze(zy, cx + 3, unter, ROLLE["leer"])
            zy += 2                          # Luft zwischen Terminen, wie calcurse
        if i < n - 1:
            lw.setze(y0 + bh - 1, cx - 1, "─" * (cw + 2), ROLLE["rahmen"])


def _a_deadline(lw, y, cx, cw, t, gewaehlt):
    """A: „⚑ 23:59 Analysis HÜ · in 2 T" — gewählt in der Akzentfläche,
    ab kalender_deadline.FLAECHE_AB als leuchtende Fläche."""
    txt = kuerzen(kalender_deadline.a_text(t), cw - 1)
    if gewaehlt:
        lw.setze(y, cx + 1, txt + " " * (cw - 1 - text_breite(txt)), _a_rolle("a_akzent") + INV)
        return
    st = kalender_deadline.stufe(t["roh"], t["tag"])
    r = ROLLE["aus"] if t["aus"] else kalender_deadline.rolle(st, t["unv"])
    if kalender_deadline.flaeche(st) and not t["unv"] and not t["aus"]:
        r += INV
    lw.setze(y, cx + 1, txt, r)


def _a_phasen(lw, y, x, platz, daten, d):
    """Leiser Hinweis auf den Tagesrhythmus links im Tageskopf („☾ 21:30
    ᶻ 23:00", kalender_motive.a_hinweis) — nur, wenn er ganz hinpasst."""
    teile = kalender_motive.a_hinweis(daten, d)
    if not teile or sum(text_breite(t) + 2 for t, _r in teile) - 2 > platz:
        return
    for text, rolle in teile:
        x = lw.setze(y, x, text, rolle) + 2


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
                r = ROLLE["tag_belegt"]
            else:
                r = ROLLE["tag_frei"]
            if inv:
                r = ROLLE["a_akzent"]          # gewählter Tag: Akzentfläche wie in B/C
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
    _sync_kopf(lw, 0, 2 + text_breite("KALENDER · %s %d" % (
        MONATE[erster.month - 1].upper(), erster.year)) + 2, breite - 1, daten)
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
        erst_t = next(iter(sp["tage"].values()))
        if erst_t["unv"] and not ist and not erst_t["stil"]:   # uncommitted: Glas statt Fläche
            lw.glas(y + 1 + bi, x0, breite, ROLLE["spanne"], _balken_text(sp, a, b, breite))
            continue
        r_balken = (_a_rolle("a_akzent") if ist else ROLLE["spanne"]) + INV
        if erst_t["stil"] and not ist:
            r_balken = kalender_stil.flaechen_rolle(r_balken, erst_t["stil"])
        lw.setze(y + 1 + bi, x0, _balken_text(sp, a, b, breite), r_balken)
    nb = min(len(bahnen_ende), platz)
    for d in sichtbar:
        x0 = 2 + d.weekday() * (cw + 1)
        if d == sel_tag:                     # gewählter Tag: Zahl in Akzentfläche
            lw.setze(y, x0, kuerzen((" %d " if d == heute else "%d ") % d.day, cw),
                     _a_rolle("a_akzent") + INV)
        elif d == heute:
            lw.setze(y, x0, kuerzen(" %d " % d.day, cw), ROLLE["heute"] + INV)
        elif _a_zyklus(daten, d):            # Zyklus-Tönung wie im Mini-Monat von A
            lw.setze(y, x0, kuerzen("%d" % d.day, cw), ROLLE["zyklus"])
        else:
            lw.setze(y, x0, kuerzen("%d" % d.day, cw),
                     ROLLE["wochenende"] if d.weekday() >= 5 else ROLLE["tag_belegt"])
        rest = [t for t in monat_eintraege(daten, d.isoformat(), erledigte)
                if not t["spanne"]]
        frei = platz - nb
        zeige = rest if len(rest) + versteckt[d] <= frei else rest[:max(0, frei - 1)]
        # Ist der gewählte Termin weggekürzt, nimmt er den letzten Platz ein.
        if d == sel_tag and sel is not None and zeige and \
                not any(_selbe(t["roh"], sel) for t in zeige):
            gew = [t for t in rest if _selbe(t["roh"], sel)]
            if gew:
                zeige = zeige[:-1] + gew
        for k, t in enumerate(zeige):
            yy = y + 1 + nb + k
            if d == sel_tag and sel is not None and _selbe(t["roh"], sel):
                txt = _b_text(t, cw)
                lw.setze(yy, x0, txt + " " * (cw - text_breite(txt)), _a_rolle("a_akzent") + INV)
                continue
            if t["deadline"]:                # Leucht-Rot mit ⚑ (kalender_deadline)
                st = kalender_deadline.stufe(t["roh"], t["tag"])
                r = ROLLE["aus"] if t["aus"] else kalender_deadline.rolle(st, t["unv"])
                txt = kuerzen(kalender_deadline.b_text(t, cw), cw)
                if kalender_deadline.flaeche(st) and not t["unv"] and not t["aus"]:
                    txt, r = txt + " " * (cw - text_breite(txt)), r + INV
                lw.setze(yy, x0, txt, r)
                continue
            if t["start"] is None and t["ende"] is None:
                # Ganztägig als Band: Fläche über die ganze Zellenbreite.
                band = kuerzen(t["label"], cw)
                gestylt = t["stil"] and not t["aus"] and not t.get("gruppe")
                if t["unv"] and not t["aus"] and not gestylt:
                    lw.glas(yy, x0, cw, _glasrolle(t), band)
                    continue
                band += " " * (cw - text_breite(band))
                r_band = _rolle(t) + ("" if t["aus"] else INV)
                lw.setze(yy, x0, band, kalender_stil.flaechen_rolle(r_band, t["stil"])
                         if gestylt else r_band)
            else:
                txt = _b_text(t, cw)
                if t.get("gruppe") and t["unv"]:
                    lw.glas(yy, x0, cw, _glasrolle(t), txt)
                    continue
                lw.setze(yy, x0, txt, kalender_stil.text_rolle(_rolle(t), t["stil"])
                         if t["stil"] and not t["aus"] and not t.get("gruppe") else _rolle(t))
        mehr = len(rest) - len(zeige) + versteckt[d]
        if mehr and frei > 0:
            lw.setze(y + 1 + nb + len(zeige), x0, kuerzen("+%d" % mehr, cw), ROLLE["leer"])


_selbe = kalender_gruppen.selbe


def _b_text(t: dict, cw: int) -> str:
    """Zellentext in B: Anfangszeit + Titel; eine Gruppe als „08:30–16:00
    Uni" (kalender_gruppen.text). Unter 9 Spalten wäre „10:…" alles, was
    übrig bleibt — dann lieber den Titel; die Uhrzeit zeigen A und C."""
    if t.get("gruppe"):
        return kuerzen(kalender_gruppen.text(t, cw), cw)
    if t.get("deadline"):
        return kuerzen(kalender_deadline.b_text(t, cw), cw)
    zeit = _hm(t["start"]) + " " if t["start"] is not None and cw >= 9 else ""
    return kuerzen(zeit + t["label"], cw)


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
# Ganztags-Zone (20.10.2026, Sasha: „ich habe 2 am freitag angelegt und es wird
# nur eins angezeigt … sie sollen sich oben stacken"): so viele Zeilen höchstens,
# darüber steht in der letzten „+n". Die Zone ist so hoch wie der Tag mit den
# meisten Ganztägigen (über die Woche einheitlich), die Zeitachse rückt darunter.
GANZTAGS_ZEILEN = 4
GANZTAGS_ACHSE_MIN = 6    # so viele Zeilen behält die Zeitachse mindestens
# Ebene „uncommitted" liegt UNTER den festen Terminen (Sasha, 22.10.2026:
# „uncommitted liegt IMMER klar unten drunter!"). Ist ein uncommitted Block so
# verdeckt, dass keine seiner Zeilen frei bleibt (sein Titel hätte keinen
# Platz), steht dieses Zeichen blass in der Randspalte rechts der Tagesspalte
# auf seiner Startzeile, darunter über seine Dauer ein gestrichelter Strich
# (gestrichelt = nicht fest, wie die uncommitted-Deadline ╍) — in seiner
# Kursfarbe, leise, ≥ 3:1. So bleibt er auffindbar. "" = kein Zeichen/Strich.
UNC_VERDECKT_ZEICHEN = "◌"
UNC_VERDECKT_STRICH = "┊"


def _c_bloecke(daten, tag: date, erledigte):
    """Zeit-Blöcke eines Tages: [(start, ende, eintrag)], die Ganztags-
    Einträge ohne Spanne (die gehören nicht auf die Achse) und die Deadlines
    (ein Zeitpunkt: eine Linie über allem, keine Bahn — kalender_deadline)."""
    bloecke, ganz, deadlines = [], [], []
    for t in _tag_eintraege(daten, tag.isoformat(), erledigte):
        s, e = t["start"], t["ende"]
        if t["deadline"]:
            deadlines.append(t)
            continue
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
    return bloecke, ganz, deadlines


# Bahnen und Rechtecke der Blöcke: kalender_ebenen.py
_c_bahnen, _c_lagen = kalender_ebenen.bahnen, kalender_ebenen.lagen


def _c_zeit(t: dict, s: int, e: int) -> str:
    """Zeitzeile eines Blocks: „10–12", „10:15–11:45"; Spannen ihre Marke
    („18→", „→14", „↔"), die sagt, dass es am Nachbartag weitergeht."""
    if t["spanne"]:
        if t["start"] is not None and t["ende"] is not None:
            return "%s–%s" % (_hm_kurz(s), _hm_kurz(e))
        if t["start"] is not None:
            return "%s→" % _hm_kurz(s)
        if t["ende"] is not None:
            return "→%s" % _hm_kurz(e)
        return "↔"
    if t["ende"] is not None and t["start"] is not None:
        return "%s–%s" % (_hm_kurz(s), _hm_kurz(e))
    return _hm_kurz(s if t["start"] is not None else e)


def _c_zeilen(t: dict, s: int, e: int, bw: int, hoch: int) -> list:
    """Beschriftung eines Blocks, Zeile für Zeile, je auf bw gekürzt.

    Sasha, 10.10.2026: „wieso divergieren manche termine, bei manchen steht
    die uhrzeit davor bei manchen nicht?" — früher stand die Zeit nur davor,
    wenn sie mit dem Titel in die Breite passte. Jetzt EINHEITLICH: Zeile 1
    ist immer nur der Titel; darunter (gedämpft, wenn der Block hoch genug
    ist) bei Quellen-Terminen der Name der Liste, dann die Zeit. Ein
    einzeiliger Block zeigt nur den Titel — die Zeit steht an der Achse."""
    zeilen = [t["label"]]
    unter = quelle_unterzeile(t)
    if unter:
        zeilen.append(unter)
    zeilen.append(_c_zeit(t, s, e))
    return [kuerzen(z, bw) for z in zeilen[:max(1, hoch)]]


def ansicht_c(daten, breite: int, hoehe: int, erledigte: bool = False,
              auswahl: dict | None = None, jetzt=None) -> list:
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
    _sync_kopf(lw, 0, 4 + text_breite("woche %d · %s" % (kw, span)) + 2, breite - 2, daten)

    tage = [_c_bloecke(daten, d, erledigte) for d in woche]
    x0 = 1 + g
    for i, d in enumerate(woche):
        r = ROLLE["heute"] if d == heute else ROLLE["zyklus"] if _a_zyklus(daten, d) else (
            ROLLE["c_wochenende"] if d.weekday() >= 5 else ROLLE["titel"])
        kopf = "%s %s" % (WT[d.weekday()], d.strftime("%d."))
        kopf = kopf if len(kopf) < colw else WT[d.weekday()][:colw - 1]
        if d == sel_tag:                     # gewählter Tag: Kopf in Akzentfläche
            r, kopf = _a_rolle("a_akzent") + INV, kopf + " " * (colw - 1 - text_breite(kopf))
        lw.setze(1, x0 + i * colw, kopf, r)
    y0 = 2 + _c_ganztags(lw, 2, hoehe, x0, g, colw, tage, sel)
    # Tagesphasen: leiser Hintergrund HINTER Punktlinien und Terminen
    phasen = [kalender_motive.tag_phasen(daten, d) for d in woche]
    fenster = _c_achse(lw, y0, hoehe - 1, x0, g, colw, tage, breite, sel, (woche, phasen))
    if fenster:                              # Jetzt-Linie: über allem, golden (kalender_jetzt)
        kalender_jetzt.c_zeichnen(lw, y0, fenster[2], fenster[0], fenster[1], woche, x0,
                                  colw, jetzt)
    return lw.zeilen()


def _c_ganztags(lw, y0, hoehe, x0, g, colw, tage, sel) -> int:
    """Die Ganztags-Zone: je Tag ALLE Ganztägigen untereinander, in der
    Reihenfolge der Auswahl (_tag_eintraege). So hoch wie der Tag mit den
    meisten, höchstens GANZTAGS_ZEILEN (die Zeitachse behält
    GANZTAGS_ACHSE_MIN); passt ein Tag nicht hinein, steht in der letzten
    Zeile „+n" — außer der gewählte Eintrag läge dahinter, dann steht er
    dort. Feste stehen oben, uncommitted danach, blass (Glas über leerem
    Grund) in eigener Zeile — nie über einem festen (22.10.2026). -> Zeilen."""
    meiste = max((len(ganz) for _b, ganz, _d in tage), default=0)
    if not meiste:
        return 0
    platz = max(1, min(GANZTAGS_ZEILEN, hoehe - 1 - y0 - GANZTAGS_ACHSE_MIN))
    zeilen = min(meiste, platz)
    lw.setze(y0, 1, kuerzen("ganzt.", g - 1), ROLLE["zeit"])
    pw = colw - 1
    for i, (_b, ganz, _d) in enumerate(tage):
        xx = x0 + i * colw
        ganz = sorted(ganz, key=lambda t: bool(t["unv"]))   # fest zuerst, uncommitted danach
        gew = next((t for t in ganz if sel is not None and t["roh"] is sel), None)
        zeige = ganz if len(ganz) <= zeilen else ganz[:max(1, zeilen - 1)]
        if gew is not None and not any(t is gew for t in zeige):
            zeige = zeige[:-1] + [gew]
        mehr = len(ganz) - len(zeige)
        for k, t in enumerate(zeige):
            # nur eine Zeile und mehr als einer: „+n" hängt am Titel
            zusatz = " +%d" % mehr if mehr and zeilen == 1 else ""
            band = kuerzen(t["label"], pw - len(zusatz)) + zusatz
            y = y0 + k
            if t is gew:
                lw.setze(y, xx, band + " " * (pw - text_breite(band)), _a_rolle("a_akzent") + INV)
            elif t["unv"] and not t["aus"] and not t["stil"]:
                lw.glas(y, xx, pw, _glasrolle(t), band)
            else:
                r_band = _rolle(t) + ("" if t["aus"] else INV)
                if t["stil"] and not t["aus"]:
                    r_band = kalender_stil.flaechen_rolle(r_band, t["stil"])
                lw.setze(y, xx, band + " " * (pw - text_breite(band)), r_band)
        if mehr and zeilen > 1:
            lw.setze(y0 + zeilen - 1, xx, kuerzen("+%d mehr" % mehr, pw), ROLLE["leer"])
    return zeilen


def _c_kursrolle(t, farbe) -> str:
    """Farbe eines Blocks in C: Spannen reihum, sonst die Kursfarbe."""
    if t["spanne"]:
        return farbe.setdefault(t["key"], SPANNEN_FARBEN[len(farbe) % len(SPANNEN_FARBEN)])
    return kurs_rolle(t)


def _c_block(lw, y0, lage, sel, farbe):
    """Ein Block deckend (fest, deaktiviert, mit Stil oder gewählt)."""
    t, s, e, bx, bw, k0, k1 = lage
    r = _c_kursrolle(t, farbe)
    gewaehlt = sel is not None and t["roh"] is sel
    if t["aus"]:
        r = ROLLE["aus"]
    if gewaehlt:                            # gewählter Termin: Akzent, deckend
        r = _a_rolle("a_akzent")
    texte = _c_zeilen(t, s, e, bw, k1 - k0 + 1)
    if t["stil"] and not t["aus"]:          # Stylebox: Rahmen, Fläche, Muster
        kalender_stil.c_block(lw, y0 + k0, bx, bw, k1 - k0 + 1, texte, r + INV,
                              t["stil"], leise_basis=r + INV + LEISE, gewaehlt=gewaehlt)
        return
    for k in range(k0, k1 + 1):
        txt = texte[k - k0] if k - k0 < len(texte) else ""
        if k == k0:                         # Titel: Schrift der Fläche
            lw.setze(y0 + k, bx, txt + " " * (bw - text_breite(txt)), r + INV)
        elif t["aus"]:
            lw.setze(y0 + k, bx, txt + "░" * (bw - text_breite(txt)), r)
        else:                               # Körper = dieselbe Fläche, Schrift leise
            lw.setze(y0 + k, bx, txt + " " * (bw - text_breite(txt)),
                     r + INV + (LEISE if txt else ""))


def _c_unv_block(lw, y0, lage, fest, rand_x, farbe):
    """Ein uncommitted Block UNTER den festen: blass (Leinwand.glas über dem,
    was darunter liegt — Punktlinien, Phasen — also eine leise Fläche in der
    Kursfarbe, Titel ≥ 3:1). Die festen kommen danach deckend darüber.

    Beschriftet werden nur Zeilen, die kein fester Block (der dieselben
    Spalten trifft) belegt: der Titel rutscht in die erste freie Zeile, der
    Rest folgt; ohne freie Zeile entfällt er, und in der Randspalte rand_x
    (rechts neben der Tagesspalte) steht UNC_VERDECKT_ZEICHEN auf der
    Startzeile, UNC_VERDECKT_STRICH über die übrigen Zeilen."""
    t, s, e, bx, bw, k0, k1 = lage
    r = _c_kursrolle(t, farbe)

    def belegt(k):
        return any(f[5] <= k <= f[6] and f[3] < bx + bw and bx < f[3] + f[4] for f in fest)

    frei = [k for k in range(k0, k1 + 1) if not belegt(k)]
    texte = _c_zeilen(t, s, e, bw, len(frei)) if frei else []
    zu_text = dict(zip(frei, texte))
    for k in range(k0, k1 + 1):
        txt = zu_text.get(k, "")
        lw.glas(y0 + k, bx, bw, r, txt,
                schrift=None if frei and k == frei[0] else ROLLE["leer"])
    if not frei:
        for k in range(k0, k1 + 1):
            zeichen = UNC_VERDECKT_ZEICHEN if k == k0 else UNC_VERDECKT_STRICH
            if zeichen:
                lw.glas(y0 + k, rand_x, 1, r, zeichen)


def _punktlinie_um_muster(lw, y, x, n):
    """Punktlinie, die einem Phasen-Zeichen Platz lässt (sonst verschwände
    eine halbe Stunde „essen" um 10:00 ganz unter der Linie)."""
    if not 0 <= y < lw.h:
        return
    for cx in range(max(0, x), min(lw.b, x + n)):
        if lw.z[y][cx] == Leinwand.LEER:
            lw.z[y][cx] = ("·", ROLLE["rahmen"])


def _c_achse(lw, y0, y_ende, x0, g, colw, tage, breite, sel=None, hintergrund=None):
    """Zeitachse von y0 bis vor y_ende. Das Fenster ist FEST 08–22 Uhr
    (Sasha, 08.10.2026: nicht für einen Nachttermin die ganze Woche
    aufziehen); der Zeilen-Takt ist der feinste, mit dem es in die Höhe
    passt. Was ganz außerhalb liegt, zeigt der Tag mit ▲ (früher) bzw.
    ▼ (später). Wird so ein Termin gewählt, rollt das Fenster zu ihm —
    für die ganze Woche, damit die Uhrzeiten links für alle Tage stimmen.
    -> (lo, takt, zeilen) des Fensters, ohne Platz None."""
    reihen = y_ende - y0
    if reihen < 1:
        return None
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
        for bloecke, _g, dls in tage:
            for s0, e0, t in bloecke + [(d["start"], d["start"] + 1, d) for d in dls]:
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
    # Zuerst die Phasen (kalender_motive): was danach kommt — Punktlinien,
    # Termine, Glas — liegt darüber. Sie verschieben das Fenster nicht und
    # zählen nicht für ▲/▼ (Sasha, 08.10.2026: fest 08–22).
    if hintergrund:
        for i, (d, ph) in enumerate(zip(*hintergrund)):
            if ph:
                kalender_motive.zeichne_spalte(lw, y0, n, lo, m, x0 + i * colw,
                                               colw - 1, d, ph)
    farbe: dict = {}
    for k in range(n):
        t = lo + k * m
        if t % lab == 0:
            lw.setze(y0 + k, 1, kuerzen(_hm(t) if g >= 6 else "%02d" % (t // 60), g - 1),
                     ROLLE["rahmen"])
            if hintergrund and kalender_motive.PUNKTLINIE_WEICHT:
                _punktlinie_um_muster(lw, y0 + k, x0, 7 * colw)
            else:
                lw.setze(y0 + k, x0, "·" * (7 * colw), ROLLE["rahmen"])
    pw = colw - 1
    for i, (bloecke, _g, _d) in enumerate(tage):
        # Zwei Ebenen (Sasha, 22.10.2026: „warum soll ein anderer termin
        # uncommitted aussehen, nur weil ein uncommitted drüber liegt??
        # uncommitted liegt IMMER klar unten drunter!"): feste Termine rechnen
        # ihre Bahnen nur unter sich, uncommitted unter sich über die volle
        # Spalte. Gezeichnet wird erst uncommitted (blass), dann die festen
        # deckend darüber — ein fester Termin sieht nie anders aus, weil
        # darunter etwas liegt. Nur der GEWÄHLTE uncommitted kommt obenauf.
        xs = x0 + i * colw
        fest = _c_lagen(_c_bahnen([b for b in bloecke if not b[2]["unv"]], (lo, m)),
                        xs, pw, lo, m, sicht_ende)
        unv = _c_lagen(_c_bahnen([b for b in bloecke if b[2]["unv"]], (lo, m)),
                       xs, pw, lo, m, sicht_ende)
        oben = []
        for lg in unv:
            t = lg[0]
            if sel is not None and t["roh"] is sel:
                oben.append(lg)
            elif t["aus"] or t["stil"]:
                _c_block(lw, y0, lg, sel, farbe)
            else:
                _c_unv_block(lw, y0, lg, fest, xs + pw, farbe)
        for lg in fest + oben:
            _c_block(lw, y0, lg, sel, farbe)
        # Ganz außerhalb des Fensters? Dann ein Pfeil in der Spalte des Tages.
        rechts = x0 + i * colw + max(0, colw - 2)
        if any(e <= lo for _s, e, _t in bloecke):
            lw.setze(y0, rechts, "▲", _a_rolle("a_akzent"))
        if any(s >= sicht_ende for s, _e, _t in bloecke):
            lw.setze(y0 + n - 1, rechts, "▼", _a_rolle("a_akzent"))
    # Deadlines zuletzt: eine hingemalte Linie ÜBER allem (kalender_deadline)
    for i, (_b, _g, dls) in enumerate(tage):
        if dls:
            kalender_deadline.c_zeichnen(lw, y0, n, lo, m, x0 + i * colw, pw, dls, sel,
                                         kuerzen=kuerzen, text_breite=text_breite,
                                         akzent=_a_rolle("a_akzent"))
    return lo, m, n
