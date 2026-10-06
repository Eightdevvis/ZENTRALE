# tui/ansichten/klavier.py
#
# Das Klavier der TUI: pure Geometrie und Belegung (piano_*, PIANO_*), dazu
# das Werkzeug selbst. Ton macht core/tone.py, erst beim Öffnen geladen —
# die einzige Ausnahme von stdlib-only (siehe Kopf von tui/zentrale_tui.py).
# Bis 06.10.2026 lag das als Modul-Helfer und Closures in zentrale_tui.py,
# siehe memory/system/tui_bauplan.md.

import atexit
import curses
import os
import subprocess
import sys
import threading
import time
import urllib.error

from .basis import PROJEKT, api_call


# ── Klavier-Werkzeug (Taste 'k') ────────────────────────────────────
# Ton macht core/tone.py: die TUI ist sonst stdlib-only, aber Klang MUSS
# auf dem Knoten entstehen, an dem der Mensch sitzt — über HTTP lässt sich
# kein Lautsprecher bedienen. Der Import passiert deshalb erst beim Öffnen
# des Panels (und darf scheitern: dann bleibt es still, Noten und Aufnahme
# laufen weiter).
def p_tone():
    """core/tone.py nachladen — None, wenn es das Modul nicht gibt."""
    try:
        core_dir = os.path.join(PROJEKT, "core")
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        import tone
        return tone
    except Exception:
        return None


def p_xset(delay, rate):
    """Tastenwiederholung des Systems setzen (X11). Best effort."""
    try:
        subprocess.run(["xset", "r", "rate", str(int(delay)), str(int(rate))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=2)
    except Exception:
        pass


# ── Klavier: pure Geometrie + Belegung (curses-frei, daher unit-testbar) ────
# Dieselbe Klaviatur wie im Browser (ui/templates/monolith.html): die
# Buchstabenreihen SIND die Tasten — untere Reihe weiß, die Reihe darüber die
# schwarzen, dort wo sie physisch dazwischen liegen. 'f' und 'k' fallen in die
# Lücken E–F und H–C, wo es keine schwarze Taste gibt, und bleiben so für ihre
# Shortcuts frei (k = Klavier zu). Halbton-Werte = Abstand über dem Grund-C.
PIANO_WHITE = [("y", 0), ("x", 2), ("c", 4), ("v", 5), ("b", 7),
               ("n", 9), ("m", 11), (",", 12), (".", 14), ("-", 16)]
# (taste, halbton, w) — w = Index der weißen Taste, an deren rechter Kante die
# schwarze sitzt.
PIANO_BLACK = [("s", 1, 0), ("d", 3, 1), ("g", 6, 3), ("h", 8, 4),
               ("j", 10, 5), ("l", 13, 7), ("ö", 15, 8)]
PIANO_KEYMAP = dict([(k, s) for k, s in PIANO_WHITE] +
                    [(k, s) for k, s, _w in PIANO_BLACK])
# Halbton → laufende Nummer der Taste (von links). Nur fürs Licht: sie sagt,
# welche Farbe der Leuchtreihe eine Taste gerade abbekommt.
PIANO_BLACK_NR = {s: i for i, (_k, s, _w) in enumerate(PIANO_BLACK)}
PIANO_WHITE_NR = {s: i for i, (_k, s) in enumerate(PIANO_WHITE)}
# Deutsche Notennamen (H statt B) — Sasha liest die Zeile, nicht ein Programm.
PIANO_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "H"]
PIANO_SEMI_TO_DIA = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]   # Halbton → Stufe
PIANO_IS_SHARP = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
PIANO_OCT_MIN, PIANO_OCT_MAX = 3, 6
PIANO_NOTE_MS = 420        # Länge eines Anschlags (Terminal kennt kein Loslassen)
PIANO_HOLLOW_MS = 500      # ab hier hohler Notenkopf (wie im Browser: lang gehalten)
PIANO_CHORD_MS = 70        # bis hierhin gilt es als gleichzeitig = eine Spalte (wie im Browser)
PIANO_LIT_MS = 260         # so lange leuchtet eine angeschlagene Taste nach
# Gedrückt halten. Das Terminal meldet kein Loslassen, aber das SYSTEM schickt
# eine gehaltene Taste wiederholt nach — das ist das Halte-Signal. Von Haus aus
# taugt es nicht: X wartet erst ~500 ms, und in diesem Loch wäre der Ton schon
# gedämpft und schlüge danach neu an (genau das hat man gehört). Fürs offene
# Klavier stellt die TUI die Wiederholung deshalb auf kurz und dicht und setzt
# sie beim Schließen zurück:
PIANO_REPEAT_DELAY = 80    # ms bis zur ersten Wiederholung (X-Standard: ~500)
PIANO_REPEAT_RATE = 30     # Wiederholungen/s → alle ~33 ms
# Kommt dieselbe Taste schneller als das wieder, ist sie gehalten; bleibt sie
# länger aus, ist der Finger weg. Zwischen 120 ms und dem, was eine Hand
# schafft (~150 ms für zweimal dieselbe Taste), liegt genug Luft.
PIANO_HOLD_MS = 120
PIANO_MAX_COLS = 64        # so viele Noten-Spalten hält das Notensystem vor
PIANO_KB_MIN_H = 5         # flacher lohnt keine gezeichnete Klaviatur
PIANO_KB_MAX_H = 13        # höher wirken die Tasten nur noch klobig
PIANO_LIGHTS = ("neon", "regenbogen", "aus")   # Taste 'L' zykliert das durch
PIANO_SHIMMER_HZ = 6.0     # Stufen pro Sekunde, mit denen der Schimmer wandert
# GROBE Rhythmus-Notation. Das Terminal meldet kein Loslassen — wie lang eine
# Note war, steht also nirgends. Was messbar IST, ist der Abstand zum nächsten
# Anschlag: wer wartet, hält. Daraus wird die Notenlänge, und was nach dem
# Runden übrig bleibt, wird zur Pause. Vier Stufen, mehr wäre Genauigkeit
# vorgetäuscht, die die Tipperei nicht hergibt.
PIANO_BEAT_MS = (250, 500, 1000, 2000)          # achtel, viertel, halbe, ganze
PIANO_BEAT_NAMES = ("achtel", "viertel", "halbe", "ganze")
PIANO_BEAT_MIN = 350       # kürzere Reste werden keine Pause (das wäre Zittern)
PIANO_BEAT_DEFAULT = 1     # Ersatzlänge, wo nichts zu messen ist (viertel)
PIANO_REST_GLYPH = ("▁", "▂", "▄", "█")   # Pause: je länger, desto höher der Block
PIANO_HOLD_GLYPH = ("", "", "─", "═")     # Halte-Strich hinter langen Noten
# Notensystem: 5 Linien im Violinschlüssel, von unten E4 bis oben F5. Eine
# Terminal-Zeile = eine diatonische Stufe (Linie ODER Zwischenraum).
PIANO_TOP_DIA = 38         # F5 = oberste Linie
PIANO_BOT_DIA = 30         # E4 = unterste Linie
PIANO_STAFF_ROWS = PIANO_TOP_DIA - PIANO_BOT_DIA + 1        # 9 Zeilen


def piano_dia(n):
    """MIDI-Note → diatonische Stufe (C0=0, jede weiße Taste eine Stufe höher).
    Das ist die Höhe im Notensystem: Halbtöne teilen sich eine Stufe."""
    n = int(n)
    return (n // 12 - 1) * 7 + PIANO_SEMI_TO_DIA[n % 12]


def piano_note_name(n):
    """MIDI-Note → deutscher Notenname mit Oktave, z.B. 60 → 'C4'."""
    n = int(n)
    return PIANO_NAMES[n % 12] + str(n // 12 - 1)


def piano_midi(octave, semi):
    """Grund-Oktave + Halbton-Offset → MIDI-Note (Oktave 4 → C4 = 60)."""
    return (int(octave) + 1) * 12 + int(semi)


def piano_keyboard(width, height=PIANO_KB_MIN_H):
    """
    Klaviatur als fertige Zeichenzeilen + Trefferzonen. PURE Funktion:
      width, height (verfügbarer Platz) -> (rows, zones)
      rows  = [str, …] von oben nach unten, alle gleich lang
      zones = [(zeile, x, breite, halbton, schwarz?, art), …] — die Stellen, die
              die TUI einfärbt. `art` sagt, WAS die Stelle ist:
                "face"  = Tastenfläche (schwarz füllen bzw. beim Anschlag leuchten)
                "frame" = Rand der schwarzen Keycap (kriegt die Leuchtfarbe)
                "label" = die eine Zelle mit dem Buchstaben
              Erst face, dann frame, dann label — in dieser Reihenfolge gemalt.

    Gezeichnet wird die Aufsicht auf eine echte Klaviatur: die weißen Tasten
    stehen als Kästchen nebeneinander, die schwarzen sind schmaler, reichen bis
    an die Hinterkante (oberste Zeile) und liegen mittig auf der Kante zwischen
    zwei weißen — vorne bleibt die weiße Taste frei, dort steht ihr Buchstabe.
    Ist die schwarze Taste breit genug (ab 3 Spalten), bekommt sie eine echte
    Keycap-Umrandung mit dem Buchstaben in der Mitte; sonst steht der Buchstabe
    wie früher unten in der Taste.
    Breite und Höhe der Tasten wachsen mit dem Platz (weiße Taste 2…9 Spalten);
    ist es zu eng oder zu flach, kommt eine leere Rückgabe und der Aufrufer
    schreibt stattdessen eine Textzeile hin.
    """
    nw = len(PIANO_WHITE)
    kw = 0
    for cand in (9, 7, 5, 3, 2):
        if nw * (cand + 1) + 1 <= max(0, width):
            kw = cand
            break
    try:
        h = int(height)
    except (TypeError, ValueError):
        h = PIANO_KB_MIN_H
    if kw == 0 or h < PIANO_KB_MIN_H:
        return [], []
    h = min(h, PIANO_KB_MAX_H)
    total = nw * (kw + 1) + 1
    # Schwarze Taste: gut halb so breit wie eine weiße und ungerade, damit sie
    # symmetrisch auf der Trennlinie sitzt. Länge ~60% der weißen (wie echt).
    kb = max(1, (kw // 2) | 1)
    hb = max(0, min(h - 3, int(round(h * 0.6)) - 1))    # letzte Zeile der schwarzen Taste

    rows = [list("┌" + "┬".join(["─" * kw] * nw) + "┐")]
    for _ in range(h - 2):
        rows.append(list("│" + "│".join([" " * kw] * nw) + "│"))
    rows.append(list("└" + "┴".join(["─" * kw] * nw) + "┘"))

    # Weiße Buchstaben nach vorn (unterste Innenzeile), mittig auf der Taste.
    for i, (k, _s) in enumerate(PIANO_WHITE):
        rows[h - 2][1 + i * (kw + 1) + (kw - 1) // 2] = k

    # Schwarze Tasten drüberlegen — sie überschreiben oben auch die Kante
    # zwischen ihren beiden weißen Nachbarn, genau das macht sie zur Taste.
    # Ab 3 Spalten Breite bekommt sie eine Keycap-Umrandung (die kriegt später
    # die Leuchtfarbe), darunter bleibt sie ein schlichter Block.
    cap = kb >= 3 and hb >= 2
    mid = max(1, hb // 2)                               # Zeile des Buchstabens
    blocked = [False] * total
    spans = {}
    for k, s, w in PIANO_BLACK:
        x = max(0, min((kw + 1) * (w + 1) - kb // 2, total - kb))
        spans[s] = x
        for j in range(kb):
            blocked[x + j] = True
        for r in range(0, hb + 1):
            for j in range(kb):
                rows[r][x + j] = " "
        if cap:
            for j, chx in enumerate("┌" + "─" * (kb - 2) + "┐"):
                rows[0][x + j] = chx
            for j, chx in enumerate("└" + "─" * (kb - 2) + "┘"):
                rows[hb][x + j] = chx
            for r in range(1, hb):
                rows[r][x] = "│"
                rows[r][x + kb - 1] = "│"
            rows[mid][x + kb // 2] = k
        else:
            rows[hb][x + (kb - 1) // 2] = k

    zones = []
    for i, (_k, s) in enumerate(PIANO_WHITE):
        x0 = 1 + i * (kw + 1)
        for r in range(hb + 1, h - 1):                  # freier Teil vorne
            zones.append((r, x0, kw, s, False, "face"))
        a, b = x0, x0 + kw                              # oben: um die schwarzen herum
        while a < b and blocked[a]:
            a += 1
        while b > a and blocked[b - 1]:
            b -= 1
        if b > a:
            for r in range(1, hb + 1):
                zones.append((r, a, b - a, s, False, "face"))
        zones.append((h - 2, x0 + (kw - 1) // 2, 1, s, False, "label"))
    for _k, s, _w in PIANO_BLACK:
        x = spans[s]
        if cap:
            for r in range(1, hb):
                zones.append((r, x + 1, kb - 2, s, True, "face"))
            zones.append((0, x, kb, s, True, "frame"))
            zones.append((hb, x, kb, s, True, "frame"))
            for r in range(1, hb):
                zones.append((r, x, 1, s, True, "frame"))
                zones.append((r, x + kb - 1, 1, s, True, "frame"))
            zones.append((mid, x + kb // 2, 1, s, True, "label"))
        else:
            for r in range(0, hb + 1):
                zones.append((r, x, kb, s, True, "face"))
            zones.append((hb, x + (kb - 1) // 2, 1, s, True, "label"))
    return ["".join(r) for r in rows], zones


def piano_columns(seq, max_cols=PIANO_MAX_COLS, chord_ms=PIANO_CHORD_MS):
    """
    Gespielte Noten zu Notensystem-SPALTEN gruppieren. PURE Funktion:
      seq = [{n, d, t}, …]  ->  [[note, …], …] (je Spalte ein Akkord)

    Fast gleichzeitig Angeschlagenes (bis chord_ms auseinander) gehört in EINE
    Spalte — sonst liest sich ein Dreiklang wie drei einzelne Töne. Dieselbe
    Toleranz wie im Browser (CHORD_MS), damit dieselbe Aufnahme in beiden
    Fronten gleich notiert erscheint. Es bleiben nur die letzten max_cols
    Spalten stehen: das Notensystem läuft mit, Rausgelaufenes ist gespielt.
    """
    cols = []
    for e in (seq or []):
        if not isinstance(e, dict):
            continue
        try:
            t = int(e.get("t", 0))
            int(e.get("n"))
        except (TypeError, ValueError):
            continue
        if cols and abs(t - cols[-1][0]) <= chord_ms:
            cols[-1][1].append(e)
        else:
            cols.append((t, [e]))
    out = [sorted(notes, key=lambda x: int(x.get("n", 0))) for _t, notes in cols]
    return out[-max_cols:] if max_cols and len(out) > max_cols else out


def piano_is_hold(gap_ms, hold_ms=PIANO_HOLD_MS):
    """
    Ist dieses erneute Ereignis DERSELBEN Taste ein Halten (True) oder ein
    zweiter Anschlag (False)? PURE Funktion, gap_ms = Abstand zum letzten
    Ereignis dieser Taste.

    Das Terminal meldet kein Loslassen — was es meldet, ist die
    TASTENWIEDERHOLUNG des Systems. Damit die eindeutig ist, stellt die TUI sie
    fürs offene Klavier auf kurz (PIANO_REPEAT_DELAY/-_RATE): die Salve setzt
    schon nach ~80 ms ein und läuft alle ~33 ms weiter. Unter `hold_ms` liegt
    also nur sie; so schnell drückt keine Hand dieselbe Taste zweimal. Bleibt
    die Salve länger aus, ist der Finger weg.
    """
    try:
        gap_ms = float(gap_ms)
    except (TypeError, ValueError):
        return False
    return 0 <= gap_ms <= float(hold_ms)


def piano_beat(ms):
    """Millisekunden → grobe Notenwert-Stufe (0 achtel … 3 ganze). PURE."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        ms = 0
    if ms < PIANO_BEAT_MIN:
        return 0
    if ms < 750:
        return 1
    if ms < 1500:
        return 2
    return 3


def piano_flow(seq, max_cols=PIANO_MAX_COLS, chord_ms=PIANO_CHORD_MS):
    """
    Was das Notensystem von links nach rechts hinschreibt — Noten UND Pausen.
    PURE Funktion:
      seq -> [("n", [note, …], stufe|None), ("p", stufe), …]

    Die Länge einer Note kommt aus dem Abstand zum NÄCHSTEN Anschlag (das
    Terminal kennt kein Loslassen, siehe PIANO_BEAT_MS): wer wartet, hält.
    Bleibt nach dem Runden auf die Stufe noch Zeit übrig, wird daraus eine
    Pause. Die letzte Note hat noch keinen Nachfolger — ihre Stufe ist `None`
    (offen, hohler Kopf), sie bekommt ihre Länge, sobald es weitergeht.

    Zwei Stellen schreiben BEWUSST keine Pause, sonst wäre das Blatt voller
    Bedenkzeit statt Musik: vor der ersten Note, und vor einer Note mit dem
    Flag `np` — das setzt die TUI nach dem Löschen mit der Rücktaste. Die Note
    davor wird dann mit der Ersatzlänge geschlossen, statt die Lücke zu messen.
    """
    cols = piano_columns(seq, max_cols=0, chord_ms=chord_ms)
    starts, breaks = [], []
    for col in cols:
        t = None
        for e in col:
            try:
                ti = int(e.get("t", 0))
            except (TypeError, ValueError):
                continue
            t = ti if t is None else min(t, ti)
        starts.append(0 if t is None else t)
        breaks.append(any(bool(e.get("np")) for e in col))

    out = []
    for i, col in enumerate(cols):
        if i > 0:
            if breaks[i]:
                out.append(("n", cols[i - 1], PIANO_BEAT_DEFAULT))
            else:
                gap = starts[i] - starts[i - 1]
                stufe = piano_beat(gap)
                out.append(("n", cols[i - 1], stufe))
                rest = gap - PIANO_BEAT_MS[stufe]
                if rest >= PIANO_BEAT_MIN:
                    out.append(("p", piano_beat(rest)))
    if cols:
        out.append(("n", cols[-1], None))          # die letzte ist noch offen
    return out[-max_cols:] if max_cols and len(out) > max_cols else out


def piano_staff(seq, height, width, lit=None):
    """
    Das Notensystem als fertiges Zeichenbild. PURE Funktion:
      (seq, höhe, breite) -> (rows, marks)
      rows  = [str, …] — Linien und Zwischenräume (Hilfslinien inklusive)
      marks = [(zeile, x, zeichen, klingt?), …] — die Notenköpfe, damit die TUI
              die gerade klingenden farbig setzen kann.

    Höhe: die 5 Linien brauchen 9 Zeilen; alles darüber wird gleichmäßig als
    Hilfslinien-Raum ober- und unterhalb verteilt. Noten außerhalb werden auf
    den Rand geklemmt (statt zu verschwinden) — bei Oktave 3 oder 6 liegt das
    Gespielte weit außerhalb des Violinschlüssels, und ein Notensystem, das
    dann leer bleibt, wäre die schlechtere Lüge.
    """
    height = int(height)
    if height < PIANO_STAFF_ROWS or width < 6:
        return [], []
    extra = height - PIANO_STAFF_ROWS
    pad_top = extra // 2
    pad_bot = extra - pad_top
    rows_n = height
    gut = 3                                   # linker Rand (Taktstrich)
    colw = 3                                  # je Spalte: [♯][kopf][luft]
    ncols = max(1, (width - gut) // colw)
    flow = piano_flow(seq, ncols)

    def row_of(dia):
        return pad_top + (PIANO_TOP_DIA - int(dia))

    grid = [[" "] * width for _ in range(rows_n)]
    # Die fünf Linien (jede zweite Stufe) über die ganze Breite.
    for d in range(PIANO_BOT_DIA, PIANO_TOP_DIA + 1, 2):
        r = row_of(d)
        for x in range(width):
            grid[r][x] = "─"
    # Taktstrich links, damit das System einen Anfang hat.
    for d in range(PIANO_BOT_DIA, PIANO_TOP_DIA + 1):
        r = row_of(d)
        if 0 <= r < rows_n:
            grid[r][0] = "│"

    lit = lit or {}
    marks = []
    mitte = row_of(PIANO_BOT_DIA + 4)             # mittlere Linie: dort ruht die Pause
    for ci, item in enumerate(flow):
        x = gut + ci * colw + 1
        if x >= width:
            break
        if item[0] == "p":                        # ── Pause ──
            g = PIANO_REST_GLYPH[max(0, min(len(PIANO_REST_GLYPH) - 1, int(item[1])))]
            if 0 <= mitte < rows_n:
                grid[mitte][x] = g
                marks.append((mitte, x, g, False))
            continue
        col, stufe = item[1], item[2]
        for e in col:
            n = int(e.get("n", 60))
            dia = piano_dia(n)
            r = row_of(dia)
            clamped = False
            if r < 0:
                r, clamped = 0, True
            elif r >= rows_n:
                r, clamped = rows_n - 1, True
            # Hilfslinien: jede LINIEN-Stufe zwischen System und Note
            if not clamped:
                step = 2 if dia > PIANO_TOP_DIA else -2
                d = PIANO_TOP_DIA + step if dia > PIANO_TOP_DIA else PIANO_BOT_DIA + step
                while (dia > PIANO_TOP_DIA and d <= dia) or (dia < PIANO_BOT_DIA and d >= dia):
                    rr = row_of(d)
                    if 0 <= rr < rows_n:
                        for xx in range(max(0, x - 1), min(width, x + 2)):
                            if grid[rr][xx] == " ":
                                grid[rr][xx] = "─"
                    d += step
            # hohl = lang gehalten oder noch offen (letzte Note) — wie im Browser
            # Achtel und Viertel voll, Halbe und Ganze hohl — wie im richtigen
            # Notensatz; die offene letzte Note zählt als lang.
            long_note = stufe is None or PIANO_BEAT_MS[stufe] > PIANO_HOLLOW_MS
            head = "◇" if clamped else ("○" if long_note else "●")
            if PIANO_IS_SHARP[n % 12] and x - 1 > 0:
                grid[r][x - 1] = "♯"
            grid[r][x] = head
            marks.append((r, x, head, bool(lit.get(n))))
            # Halbe/Ganze kriegen einen Halte-Strich in die Luftspalte daneben —
            # sonst sähen sie aus wie eine Viertel (beide hohl).
            hold = PIANO_HOLD_GLYPH[stufe] if stufe is not None else ""
            if hold and x + 1 < width and grid[r][x + 1] in (" ", "─"):
                grid[r][x + 1] = hold
    return ["".join(r) for r in grid], marks


class Klavier:
    """Das Klavier (Mitte, Taste 'k'): Klaviatur auf der Computertastatur,
    Notensystem, Aufnahme und Melodien (/api/melodies), Ton über core/tone.py
    auf diesem Knoten. Zustand in self.PIANO (auch z.PIANO)."""

    def __init__(self, z):
        self.z = z
        # ── Klavier (füllt die MITTE-Box, Taste 'k') ────────────────────────
        # Das Pendant zum Klavier-Exhibit des Browsers: unten die gezeichneten
        # Tasten, darüber das Notensystem, in das das Gespielte läuft. Gespielt
        # wird auf der Computertastatur (PIANO_KEYMAP), den Ton rechnet core/tone.py
        # selbst und schiebt ihn über sounddevice raus — kein Sample, offline.
        # Aufnahmen liegen wie im Browser serverseitig (/api/melodies →
        # data/melodies.json), beide Fronten sehen also dieselben Melodien.
        #
        # EIN Unterschied zum Browser, der sich nicht wegprogrammieren lässt: das
        # Terminal meldet nur Tastendrücke, kein Loslassen. Eine Haltedauer ist
        # hier nicht messbar → jeder Anschlag klingt PIANO_NOTE_MS lang aus (wie
        # eine angeschlagene Saite). Im Browser aufgenommene Melodien behalten ihre
        # echten Haltedauern und klingen hier auch so.
        #   active : Panel hat den Fokus
        #   oct    : Grund-Oktave der untersten weißen Taste (←→, C3…C6)
        #   lit    : midi → Zeitpunkt, bis zu dem die Taste aufleuchtet
        #   seq    : was im Notensystem steht ([{n,d,t}], t = Akkord-Gruppierung)
        #   rec    : {t0, notes} solange aufgezeichnet wird, sonst None
        #   naming : nach dem Stoppen den Namen tippen (Freitext) — None = nicht
        #   mel/sel: gespeicherte Melodien + Auswahl-Cursor
        #   play   : laufende Wiedergabe (tone.Playback) oder None
        #   synth  : offener Ton-Ausgang (tone.Synth) oder None = noch nicht auf
        #   sound  : macht dieser Knoten Ton? (False = stumm, Grund steht in msg)
        self.PIANO = z.PIANO = {"active": False, "oct": 4, "lit": {}, "seq": [], "rec": None,
                                "naming": None, "mel": [], "sel": 0, "play": None,
                                "synth": None, "sound": False, "confirm": False,
                                "renaming": None, "msg": "", "_u8": b"",
                                "opening": None,      # seit wann geht das Audio-Gerät auf? (None = fertig)
                                "light": PIANO_LIGHTS[0],   # Tastenbeleuchtung: neon|regenbogen|aus ('L')
                                "held": {},           # gedrückt gehaltene Tasten (Tastenwiederholung)
                                "fastrep": False,     # läuft die Tastenwiederholung gerade schnell?
                                "repeat0": None,      # wie sie vorher stand (zum Zurücksetzen)
                                "t0": 0.0}            # Zeitnullpunkt der Noten im System

    def p_repeat_fast(self, an):
        """Solange gespielt wird, läuft die Tastenwiederholung kurz und dicht —
        nur so ist »gehalten« von »nochmal gedrückt« zu trennen UND der Ton
        reißt zwischen Anschlag und erster Wiederholung nicht ab (mit den
        voreingestellten ~500 ms wäre er längst gedämpft und schlüge neu an).

        Beim Tippen (Melodie benennen) wird zurückgestellt: mit 80 ms
        Verzögerung verdoppelt sonst jeder etwas längere Tastendruck Buchstaben.
        Der Ursprungszustand wird einmal gemerkt und immer wieder gesetzt, auch
        wenn die TUI unsanft endet (atexit) — sonst bliebe die Tastatur des
        ganzen Rechners auf hektisch stehen.
        """
        PIANO = self.PIANO
        if not os.environ.get("DISPLAY") or bool(an) == PIANO.get("fastrep"):
            return
        vor = PIANO.get("repeat0")
        if vor is None:
            vor = (500, 20)                       # X-Standard, falls nicht lesbar
            try:
                out = subprocess.run(["xset", "q"], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=2).stdout
                txt = (out or b"").decode("utf-8", "replace")
                d = int(txt.split("auto repeat delay:")[1].split()[0])
                r = int(txt.split("repeat rate:")[1].split()[0])
                if d > 0 and r > 0 and (d, r) != (PIANO_REPEAT_DELAY, PIANO_REPEAT_RATE):
                    vor = (d, r)
                # Steht schon unser Spiel-Wert da, endete die letzte TUI unsanft
                # (SIGKILL überspringt atexit). Dann ist das NICHT der
                # Ursprungszustand — lieber auf den X-Standard zurück, sonst
                # bliebe die Tastatur für immer auf hektisch.
            except Exception:
                pass
            PIANO["repeat0"] = vor
            atexit.register(lambda: p_xset(vor[0], vor[1]))
        p_xset(*(PIANO_REPEAT_DELAY, PIANO_REPEAT_RATE) if an else vor)
        PIANO["fastrep"] = bool(an)

    def p_sound_up(self):
        """Ton-Ausgang öffnen (Hintergrund-Thread: das Gerät aufzumachen kostet
        auf dem Pi spürbar Zeit, die Zeichenschleife soll nicht warten).

        Das kann auch HÄNGEN: läuft der System-Default über einen Audio-Server,
        der gerade nicht erreichbar ist (PipeWire ohne Session), blockiert
        PortAudio beim Öffnen — abbrechen lässt sich das aus Python nicht.
        Darum läuft es hier im Daemon-Thread und der Kopf des Panels sagt, in
        welchem Zustand der Ton steckt (ZENTRALE_AUDIO_DEVICE=0 o.ä. geht dann
        direkt auf die Soundkarte)."""
        PIANO = self.PIANO
        PIANO["opening"] = time.time()
        try:
            if os.environ.get("ZENTRALE_NO_AUDIO"):
                # Bewusst still: Testläufe (Fuzzer) und Knoten, die keinen Ton
                # machen sollen, öffnen gar kein Gerät.
                PIANO["sound"] = False
                PIANO["msg"] = "stumm (ZENTRALE_NO_AUDIO)"
                return
            tone = p_tone()
            if tone is None:
                PIANO["sound"] = False
                PIANO["msg"] = "stumm (core/tone.py fehlt)"
                return
            syn = tone.Synth()
            if syn.start():
                PIANO["synth"] = syn
                PIANO["sound"] = True
            else:
                PIANO["sound"] = False
                PIANO["msg"] = "stumm: " + (syn.error or "kein audio")
        finally:
            PIANO["opening"] = None

    def p_load(self):
        """Gespeicherte Melodien holen (dieselbe Quelle wie der Browser)."""
        PIANO = self.PIANO
        try:
            mel = api_call("/api/melodies")
        except (urllib.error.URLError, OSError, ValueError):
            mel = None
        if isinstance(mel, list):
            PIANO["mel"] = mel
            PIANO["sel"] = max(0, min(PIANO["sel"], len(mel) - 1))

    def p_open(self):
        PIANO, p_load, p_sound_up = self.PIANO, self.p_load, self.p_sound_up
        PIANO["active"] = True
        PIANO["seq"] = []; PIANO["lit"] = {}; PIANO["rec"] = None
        PIANO["naming"] = None; PIANO["renaming"] = None
        PIANO["confirm"] = False; PIANO["msg"] = ""; PIANO["_u8"] = b""
        PIANO["t0"] = time.time()
        threading.Thread(target=p_sound_up, daemon=True).start()
        threading.Thread(target=p_load, daemon=True).start()

    def p_close(self):
        PIANO, p_repeat_fast, p_stop_play = self.PIANO, self.p_repeat_fast, self.p_stop_play
        p_stop_play()
        PIANO["rec"] = None
        syn = PIANO.get("synth")
        if syn is not None:
            try:
                syn.close()
            except Exception:
                pass
        PIANO["synth"] = None; PIANO["sound"] = False
        p_repeat_fast(False)          # Tastatur des Rechners zurückstellen
        PIANO["active"] = False; PIANO["lit"] = {}; PIANO["held"] = {}

    def p_strike(self, midi, dur_ms=PIANO_NOTE_MS, record=True, hold=False):
        """Einen Ton anschlagen: klingen lassen, Taste aufleuchten, ins
        Notensystem schreiben und (wenn aufgenommen wird) mitschneiden.
        Gibt die geschriebenen Einträge zurück (System, Aufnahme) — die
        Halte-Erkennung braucht sie, um sie notfalls wieder wegzunehmen."""
        PIANO = self.PIANO
        now = time.time()
        syn = PIANO.get("synth")
        if syn is not None:
            try:
                syn.strike(midi, dur_ms=dur_ms, hold=hold)
            except Exception:
                pass
        PIANO["lit"][midi] = now + PIANO_LIT_MS / 1000.0
        t_ms = int((now - PIANO.get("t0", now)) * 1000)
        note = {"n": int(midi), "d": int(dur_ms), "t": t_ms}
        if PIANO.pop("nopause", False):
            # Nach dem Löschen: die Lücke davor ist Bedenkzeit, keine Pause.
            note["np"] = 1
        PIANO["seq"].append(note)
        if len(PIANO["seq"]) > 96:
            del PIANO["seq"][0:len(PIANO["seq"]) - 96]
        recnote = None
        rec = PIANO.get("rec")
        if record and rec is not None:
            recnote = {"n": int(midi),
                       "t": int((now - rec["t0"]) * 1000),
                       "d": int(dur_ms)}
            rec["notes"].append(recnote)
        return note, recnote

    def p_undo_note(self):
        """Rücktaste: die zuletzt geschriebene Note wieder weg — wie im Text.
        Ein Anschlag = eine Note, also verschwindet auch genau einer (bei einem
        Akkord der zuletzt getippte Ton, nicht der ganze Griff). Die Lücke, die
        beim Überlegen entsteht, darf danach KEINE Pause werden: das merkt sich
        `nopause` für den nächsten Anschlag."""
        PIANO = self.PIANO
        if not PIANO["seq"]:
            PIANO["msg"] = "nichts zu löschen"
            return
        weg = PIANO["seq"].pop()
        PIANO["nopause"] = True
        rec = PIANO.get("rec")
        if rec is not None and rec["notes"]:
            rec["notes"].pop()          # aus der Aufnahme fällt sie genauso raus
        PIANO["msg"] = "%s weg" % piano_note_name(weg.get("n", 60))

    def p_press(self, midi):
        """Ein Tasten-Ereignis am Klavier — echter Anschlag ODER die
        Tastenwiederholung einer gehaltenen Taste (siehe piano_is_hold). Beim
        Halten passiert bewusst NICHTS außer weiterleuchten: der Ton läuft, die
        Note steht schon da."""
        PIANO, p_strike = self.PIANO, self.p_strike
        now = time.time()
        h = PIANO["held"].get(midi)
        if h is not None and piano_is_hold((now - h["t"]) * 1000.0):
            h["t"] = now
            PIANO["lit"][midi] = now + PIANO_LIT_MS / 1000.0
            syn = PIANO.get("synth")
            if syn is not None:
                try:
                    if not syn.holding(midi):     # so lange gehalten, dass der
                        syn.strike(midi, hold=True)   # Ton schon verklungen war
                except Exception:
                    pass
            return
        note, recnote = p_strike(midi, hold=True)
        PIANO["held"][midi] = {"t": now, "t0": now, "note": note, "rec": recnote}

    def p_hold_tick(self):
        """Bleibt die Wiederholung aus, ist der Finger weg: Ton ausklingen
        lassen und die wirklich gehaltene Dauer in die Note schreiben (im
        Browser klingt sie dann genauso lang)."""
        PIANO = self.PIANO
        now = time.time()
        grenze = PIANO_HOLD_MS / 1000.0
        for midi, h in list(PIANO["held"].items()):
            if now - h["t"] <= grenze:
                continue
            del PIANO["held"][midi]
            syn = PIANO.get("synth")
            if syn is not None:
                try:
                    syn.release(midi)
                except Exception:
                    pass
            gehalten = max(PIANO_NOTE_MS, int((h["t"] - h["t0"]) * 1000) + PIANO_NOTE_MS)
            for ref in (h.get("note"), h.get("rec")):
                if isinstance(ref, dict):
                    ref["d"] = gehalten

    def p_play_key(self, name):
        """Buchstaben-Taste → Ton (None, wenn die Taste keine Klaviertaste ist)."""
        PIANO, p_press = self.PIANO, self.p_press
        if name not in PIANO_KEYMAP:
            return False
        p_press(piano_midi(PIANO["oct"], PIANO_KEYMAP[name]))
        return True

    def p_shift_oct(self, d):
        PIANO = self.PIANO
        o = max(PIANO_OCT_MIN, min(PIANO_OCT_MAX, PIANO["oct"] + d))
        if o != PIANO["oct"]:
            PIANO["oct"] = o; PIANO["msg"] = ""

    # ── Aufnahme ────────────────────────────────────────────────────────
    def p_rec_toggle(self):
        """Leertaste: aufnehmen an/aus. Beim Stoppen fragt das Panel nach dem
        Namen — abgebrochen wird nichts heimlich gespeichert."""
        PIANO, p_stop_play = self.PIANO, self.p_stop_play
        if PIANO["rec"] is not None:
            rec = PIANO["rec"]; PIANO["rec"] = None
            if not rec["notes"]:
                PIANO["msg"] = "aufnahme leer — nichts gespeichert"
                return
            # Der Vorschlag steht NICHT im Tipppuffer (sonst hängt das Getippte
            # hinten dran: „melodie 1testlied"). Er gilt, wenn nichts getippt
            # wird — wie ein Browser-prompt mit vorausgewähltem Default.
            PIANO["naming"] = {"notes": rec["notes"], "buf": "",
                               "vorschlag": "melodie %d" % (len(PIANO["mel"]) + 1)}
            PIANO["msg"] = ""
            return
        p_stop_play()
        PIANO["rec"] = {"t0": time.time(), "notes": []}
        PIANO["msg"] = ""

    def p_save(self, name, notes):
        """Aufnahme ans Backend (Hintergrund-Thread — POST darf nicht blocken)."""
        PIANO, p_load = self.PIANO, self.p_load
        def _do():
            try:
                m = api_call("/api/melodies", "POST", {"name": name, "notes": notes})
            except (urllib.error.URLError, OSError, ValueError):
                m = None
            if isinstance(m, dict) and m.get("id"):
                PIANO["msg"] = "gespeichert: " + str(m.get("name"))
                p_load()
            else:
                PIANO["msg"] = "speichern fehlgeschlagen (backend?)"
        threading.Thread(target=_do, daemon=True).start()

    # ── Wiedergabe ──────────────────────────────────────────────────────
    def p_sel_melody(self):
        PIANO = self.PIANO
        mel = PIANO["mel"]
        if not mel:
            return None
        return mel[max(0, min(PIANO["sel"], len(mel) - 1))]

    def p_stop_play(self):
        PIANO = self.PIANO
        pl = PIANO.get("play")
        PIANO["play"] = None
        if pl is not None:
            try:
                pl.stop()
            except Exception:
                pass
        syn = PIANO.get("synth")
        if syn is not None:
            try:
                syn.silence()
            except Exception:
                pass

    def p_play(self):
        """Ausgewählte Melodie abspielen (nochmal enter = abbrechen). Die Noten
        laufen dabei live ins Notensystem — man sieht, was man hört."""
        PIANO, p_sel_melody, p_stop_play = self.PIANO, self.p_sel_melody, self.p_stop_play
        if PIANO.get("play") is not None:
            p_stop_play(); PIANO["msg"] = "abgebrochen"
            return
        m = p_sel_melody()
        if not m:
            PIANO["msg"] = "noch keine melodie — leertaste nimmt auf"
            return
        tone = p_tone()
        syn = PIANO.get("synth")
        if tone is None or syn is None:
            PIANO["msg"] = "stumm — nur die noten laufen"
        PIANO["seq"] = []; PIANO["t0"] = time.time()
        notes = m.get("notes") or []

        def _on(n, dur):
            # Den Ton macht die Wiedergabe selbst (tone.Playback) — hier nur
            # Taste aufleuchten und die Note ins Notensystem schreiben.
            now = time.time()
            PIANO["lit"][n] = now + PIANO_LIT_MS / 1000.0
            PIANO["seq"].append({"n": int(n), "d": int(dur),
                                 "t": int((now - PIANO["t0"]) * 1000)})
            if len(PIANO["seq"]) > 96:
                del PIANO["seq"][0:len(PIANO["seq"]) - 96]

        def _done():
            PIANO["play"] = None

        if tone is not None and syn is not None:
            PIANO["play"] = tone.play_sequence(syn, notes, on_note=_on, on_done=_done)
        else:
            # Ohne Ton wenigstens die Noten durchlaufen lassen (stummer Knoten).
            def _silent():
                t0 = time.time()
                for e in sorted(notes, key=lambda x: int(x.get("t", 0))):
                    if PIANO.get("play") is None:
                        return
                    wait = t0 + int(e.get("t", 0)) / 1000.0 - time.time()
                    if wait > 0:
                        time.sleep(min(wait, 5.0))
                    _on(int(e.get("n", 60)), int(e.get("d", PIANO_NOTE_MS) or PIANO_NOTE_MS))
                PIANO["play"] = None
            PIANO["play"] = threading.Thread(target=_silent, daemon=True)
            PIANO["play"].start()
        PIANO["msg"] = "spielt: " + str(m.get("name", ""))

    def p_rename(self, name):
        PIANO, p_load, p_sel_melody = self.PIANO, self.p_load, self.p_sel_melody
        m = p_sel_melody()
        if not m:
            return
        mid = m.get("id")

        def _do():
            try:
                r = api_call("/api/melodies/%s/rename" % mid, "POST", {"name": name})
            except (urllib.error.URLError, OSError, ValueError):
                r = None
            PIANO["msg"] = "umbenannt" if isinstance(r, dict) else "umbenennen fehlgeschlagen"
            p_load()
        threading.Thread(target=_do, daemon=True).start()

    def p_delete(self):
        PIANO, p_load, p_sel_melody = self.PIANO, self.p_load, self.p_sel_melody
        m = p_sel_melody()
        if not m:
            return
        mid = m.get("id")

        def _do():
            try:
                api_call("/api/melodies/%s" % mid, "DELETE")
            except (urllib.error.URLError, OSError, ValueError):
                PIANO["msg"] = "löschen fehlgeschlagen"
                return
            PIANO["msg"] = "gelöscht"
            p_load()
        PIANO["sel"] = max(0, PIANO["sel"] - 1)
        threading.Thread(target=_do, daemon=True).start()

    def p_lit_now(self):
        """Welche Tasten leuchten gerade? (abgelaufene rausräumen)"""
        PIANO, p_hold_tick = self.PIANO, self.p_hold_tick
        p_hold_tick()                  # losgelassene Tasten zuerst ausklingen lassen
        now = time.time()
        lit = {n: 1 for n, until in list(PIANO["lit"].items()) if until > now}
        if len(lit) != len(PIANO["lit"]):
            PIANO["lit"] = {n: until for n, until in PIANO["lit"].items() if until > now}
        for n in PIANO["held"]:
            lit[n] = 1                 # gedrückt gehalten = leuchtet, ohne Flackern
        return lit

    def oeffnen(self):
        """Startseite → Klavier (p_open: Melodien laden, Ton im Hintergrund an)."""
        self.p_open()

    def taste(self, ch):
        """Eine Taste, während das Klavier den Fokus hat (früher ein Zweig der
        Hauptschleife in run_ui)."""
        PIANO, cycle_theme, p_close = self.PIANO, self.z.cycle_theme, self.p_close
        p_delete, p_play, p_play_key = self.p_delete, self.p_play, self.p_play_key
        p_rec_toggle, p_rename, p_save = self.p_rec_toggle, self.p_rename, self.p_save
        p_sel_melody, p_shift_oct = self.p_sel_melody, self.p_shift_oct
        p_undo_note = self.p_undo_note
        # Reihenfolge zählt: erst die Freitext-Zustände (Namen tippen),
        # dann Steuertasten, ZULETZT die Klaviatur — sonst würde 'd'
        # (= D♯ bzw. löschen) im falschen Zustand landen.
        if PIANO["naming"] is not None:                 # Name der Aufnahme
            nm = PIANO["naming"]
            if ch == 27:
                PIANO["naming"] = None; PIANO["msg"] = "aufnahme verworfen"
            elif ch in (10, 13, curses.KEY_ENTER):
                name = nm["buf"].strip() or nm.get("vorschlag", "")
                if name:
                    p_save(name, nm["notes"]); PIANO["naming"] = None
                else:
                    PIANO["msg"] = "name fehlt"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                nm["buf"] = nm["buf"][:-1]
            elif 32 <= ch <= 126 and len(nm["buf"]) < 60:
                nm["buf"] += chr(ch)
            elif ch >= 128:                             # UTF-8 best effort (Umlaute)
                buf = PIANO.get("_u8", b"") + bytes([ch & 0xFF])
                try:
                    nm["buf"] += buf.decode("utf-8"); PIANO["_u8"] = b""
                except UnicodeDecodeError:
                    PIANO["_u8"] = buf if len(buf) < 4 else b""
        elif PIANO["renaming"] is not None:             # Melodie umbenennen
            if ch == 27:
                PIANO["renaming"] = None
            elif ch in (10, 13, curses.KEY_ENTER):
                name = PIANO["renaming"].strip()
                if name:
                    p_rename(name); PIANO["renaming"] = None
                else:
                    PIANO["msg"] = "name fehlt"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                PIANO["renaming"] = PIANO["renaming"][:-1]
            elif 32 <= ch <= 126 and len(PIANO["renaming"]) < 60:
                PIANO["renaming"] += chr(ch)
            elif ch >= 128:
                buf = PIANO.get("_u8", b"") + bytes([ch & 0xFF])
                try:
                    PIANO["renaming"] += buf.decode("utf-8"); PIANO["_u8"] = b""
                except UnicodeDecodeError:
                    PIANO["_u8"] = buf if len(buf) < 4 else b""
        elif PIANO["confirm"]:                          # Melodie löschen? j/n
            if ch in (ord("j"), ord("J")):
                p_delete(); PIANO["confirm"] = False
            elif ch in (ord("n"), ord("N"), 27):
                PIANO["confirm"] = False
        elif ch == 27 or ch in (ord("k"), ord("K")):    # zu (k wie im Browser)
            p_close()
        elif ch in (curses.KEY_BACKSPACE, 127, 8):      # letzte note weg
            p_undo_note()
        elif ch == ord(" "):                            # aufnehmen an/aus
            p_rec_toggle()
        elif ch in (10, 13, curses.KEY_ENTER):          # melodie spielen/abbrechen
            p_play()
        elif ch == curses.KEY_LEFT:
            p_shift_oct(-1)
        elif ch == curses.KEY_RIGHT:
            p_shift_oct(1)
        elif ch == curses.KEY_UP:
            if PIANO["mel"]:
                PIANO["sel"] = max(0, PIANO["sel"] - 1)
        elif ch == curses.KEY_DOWN:
            if PIANO["mel"]:
                PIANO["sel"] = min(len(PIANO["mel"]) - 1, PIANO["sel"] + 1)
        elif ch in (ord("r"), ord("R")):                # ausgewählte umbenennen
            m = p_sel_melody()
            PIANO["renaming"] = str(m.get("name", "")) if m else None
            if m is None:
                PIANO["msg"] = "keine melodie"
        elif ch == ord("D"):
            # Löschen liegt auf SHIFT+D: das nackte 'd' ist hier eine
            # Klaviertaste (D♯) und darf keine Melodie wegwerfen.
            if PIANO["mel"]:
                PIANO["confirm"] = True
            else:
                PIANO["msg"] = "keine melodie"
        elif ch == ord("L"):                # Tastenbeleuchtung zyklieren
            # Groß-L, weil das nackte 'l' die Taste A♯ ist.
            i = PIANO_LIGHTS.index(PIANO.get("light", PIANO_LIGHTS[0]))
            PIANO["light"] = PIANO_LIGHTS[(i + 1) % len(PIANO_LIGHTS)]
            PIANO["msg"] = "licht: " + PIANO["light"]
        elif ch in (ord("t"), ord("T")):    # Theme darf auch hier zyklieren
            cycle_theme()
        elif 32 <= ch <= 126 and chr(ch).lower() in PIANO_KEYMAP:
            p_play_key(chr(ch).lower())
        elif ch >= 128:                                 # 'ö' kommt als UTF-8 (2 bytes)
            buf = PIANO.get("_u8", b"") + bytes([ch & 0xFF])
            try:
                s = buf.decode("utf-8"); PIANO["_u8"] = b""
                if not p_play_key(s.lower()):
                    PIANO["msg"] = ""
            except UnicodeDecodeError:
                PIANO["_u8"] = buf if len(buf) < 4 else b""

    def draw_piano_tool(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box fürs Klavier: unten die Tasten, darüber das
        Notensystem — dieselbe Anordnung wie im Browser-Exhibit."""
        C, PIANO, addclip, p_lit_now = self.z.C, self.PIANO, self.z.addclip, self.p_lit_now
        p_repeat_fast = self.p_repeat_fast
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if iw < 12:
            return
        # Schnelle Tastenwiederholung nur beim Spielen, nicht beim Tippen.
        p_repeat_fast(PIANO["naming"] is None and PIANO["renaming"] is None)
        lit = p_lit_now()

        # ── Kopfzeile: Oktave, Ton-Zustand, Aufnahme ──
        rng = "%s–%s" % (piano_note_name(piano_midi(PIANO["oct"], 0)),
                         piano_note_name(piano_midi(PIANO["oct"], 16)))
        head = "okt %d  %s" % (PIANO["oct"], rng)
        if PIANO["rec"] is not None:
            el = int(time.time() - PIANO["rec"]["t0"])
            head += "   ● aufnahme %d:%02d (%d)" % (el // 60, el % 60,
                                                    len(PIANO["rec"]["notes"]))
        elif PIANO.get("opening"):
            # Gerät geht gerade auf — und wenn das zu lange dauert, sagen wir
            # das auch, statt den Nutzer auf Ton warten zu lassen, der nicht kommt.
            wartet = time.time() - PIANO["opening"]
            head += ("   ♪ ton reagiert nicht (ZENTRALE_AUDIO_DEVICE setzen?)"
                     if wartet > 4 else "   ♪ ton öffnet…")
        elif not PIANO["sound"]:
            head += "   ♪ stumm"
        if PIANO.get("light", PIANO_LIGHTS[0]) != PIANO_LIGHTS[0]:
            head += "   ✦ licht " + PIANO["light"]      # nur wenn NICHT Standard
            if not C.get("keyframe"):    # helles Theme: es gibt nichts zu färben
                head += " (nur nachts)"
        addclip(by + 1, ix, head, iw,
                C["warn"] if PIANO["rec"] is not None else C["bright"])

        # ── Klaviatur (unten) ──
        # Sie darf so groß werden, wie über dem Notensystem (PIANO_STAFF_ROWS)
        # und der Melodien-Zeile übrig bleibt — aber nie unter ihre Mindesthöhe:
        # gespielt wird auf den Tasten, das System muss dann eben weichen.
        frei = bottom - 1 - (by + 2)
        kb_h = max(PIANO_KB_MIN_H, min(PIANO_KB_MAX_H, frei - PIANO_STAFF_ROWS - 1))
        kb_rows, zones = piano_keyboard(iw, min(kb_h, frei - 1))
        if not kb_rows:
            # Zu schmal/flach für gezeichnete Tasten → wenigstens sagen, worauf
            # man spielt (statt einer leeren Fläche).
            addclip(bottom - 1, ix, "tasten: y x c v b n m , . -", iw, C["faint"])
        kb_h = len(kb_rows)
        kb_top = bottom - 1 - kb_h
        kx = ix + max(0, (iw - len(kb_rows[0] if kb_rows else "")) // 2)   # mittig
        for i, ln in enumerate(kb_rows):
            addclip(kb_top + i, kx, ln, max(0, iw - (kx - ix)), C["faint"])
        base = piano_midi(PIANO["oct"], 0)
        # Tastenbeleuchtung: "neon" = jede Keycap trägt ihre eigene Farbe,
        # "regenbogen" = dieselben Farben wandern (und die weißen Buchstaben
        # glühen mit), "aus" = wie ein normales Klavier. Der Schimmer läuft
        # über die Uhr, nicht über einen Zähler — dann ist er unabhängig davon,
        # wie oft gerade neu gezeichnet wird.
        pal, glow = C.get("keyframe") or [], C.get("keyglow") or []
        licht = PIANO.get("light", PIANO_LIGHTS[0])
        schimmer = licht == "regenbogen"
        ph = int(time.time() * PIANO_SHIMMER_HZ) if schimmer else 0
        for (r, x, w, semi, black, art) in zones:
            y = kb_top + r
            if y < by + 1 or y > bottom:
                continue
            on = lit.get(base + semi)
            seg = kb_rows[r][x:x + w]
            if black:
                if on:                                  # angeschlagen: ganze Taste
                    attr = C["key_press"]
                elif art == "frame" and pal and licht != "aus":
                    attr = pal[(PIANO_BLACK_NR.get(semi, 0) + ph) % len(pal)]
                else:
                    attr = C["key_black"]
            elif on:
                attr = C["acc"] | curses.A_REVERSE
            elif art == "label" and schimmer and glow:
                attr = glow[(PIANO_WHITE_NR.get(semi, 0) + ph) % len(glow)]
            else:
                continue                                # unberührte weiße Fläche
            addclip(y, kx + x, seg, max(0, iw - (kx - ix) - x), attr)

        # ── Notensystem (zwischen Kopfzeile und Klaviatur) ──
        st_top = by + 2
        st_h = kb_top - st_top - 1
        if st_h >= PIANO_STAFF_ROWS:
            # Das System darf die freie Höhe ausnutzen: die 5 Linien bleiben in
            # der Mitte, der Rest wird Hilfslinien-Raum. Ab ~22 Zusatzzeilen ist
            # der ganze Tastatur-Umfang (C3…C6) sichtbar, mehr bringt nichts.
            st_h = min(st_h, PIANO_STAFF_ROWS + 22)
            rows, marks = piano_staff(PIANO["seq"], st_h, iw, lit)
            for i, ln in enumerate(rows):
                addclip(st_top + i, ix, ln, iw, C["faint"])
            for (r, x, chx, now_on) in marks:
                addclip(st_top + r, ix + x, chx, max(0, iw - x),
                        C["acc"] | curses.A_BOLD if now_on else C["ink"] | curses.A_BOLD)
        elif st_h > 0:
            addclip(st_top, ix, "(fenster zu flach fürs notensystem)", iw, C["faint"])

        # ── Melodien-Zeile direkt über der Klaviatur ──
        mrow = kb_top - 1
        if mrow > st_top:
            mel = PIANO["mel"]
            if PIANO["naming"] is not None:
                nm = PIANO["naming"]
                zeile = "name: " + nm["buf"] + "_"
                if not nm["buf"]:                  # leer → der Vorschlag gilt
                    zeile += "  (enter = »%s«)" % nm.get("vorschlag", "")
                addclip(mrow, ix, zeile, iw, C["bright"])
            elif PIANO["renaming"] is not None:
                addclip(mrow, ix, "neuer name: " + PIANO["renaming"] + "_", iw, C["bright"])
            elif PIANO["confirm"]:
                addclip(mrow, ix, "melodie löschen? j/n", iw, C["warn"])
            elif mel:
                i = max(0, min(PIANO["sel"], len(mel) - 1))
                m = mel[i]
                dur = int(m.get("dur", 0) or 0) // 1000
                addclip(mrow, ix, "♪ %d/%d  %s  %d:%02d" % (
                    i + 1, len(mel), str(m.get("name", "?")), dur // 60, dur % 60),
                    iw, C["acc"] if PIANO.get("play") is not None else C["ink"])
            else:
                addclip(mrow, ix, "noch keine melodie aufgenommen", iw, C["faint"])

        # ── Statuszeile ──
        if PIANO["naming"] is not None:
            tip = "enter speichern · esc verwerfen"
        elif PIANO["renaming"] is not None:
            tip = "enter übernehmen · esc abbrechen"
        elif PIANO["confirm"]:
            tip = "j löschen · n abbrechen"
        else:
            # Welche Taste welchen Ton spielt, steht auf der Taste selbst —
            # hier nur, was man sonst nirgends sieht.
            tip = ("←→ oktave · ⌫ note weg · space aufnahme · ↑↓ melodie · "
                   "enter spielen · r name · D melodie weg · L licht · k/esc zu")
        addclip(bottom, ix, (tip + ("  " + PIANO["msg"] if PIANO["msg"] else "")).strip(),
                iw, C["faint"])
