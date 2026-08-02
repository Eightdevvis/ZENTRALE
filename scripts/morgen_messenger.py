#!/usr/bin/env python3
# scripts/morgen_messenger.py
#
# Der Morgen-Messenger — das FENSTER. Ein kleines curses-Fenster, das
# aufgeht, sobald der Laptop morgens hochkommt, und drei Dinge abarbeitet:
#
#   1. Schlaf: wann eingeschlafen, wann aufgewacht → in den »sleep«-Graphen.
#      (Überspringen mit s — dann kommt die Frage heute nicht wieder.)
#   2. Die oberste offene Aufgabe der »week«-Liste anbieten: übernehmen?
#   3. Die übernommene Aufgabe erledigen (mit y/n-Rückfrage) oder auf einen
#      Zeitpunkt vertagen — dann rückt die nächste Aufgabe nach.
#
# Kassetten-Prinzip: dieses File ZEICHNET nur und liest Tasten. Was fällig
# ist, was gespeichert wird, wie ein Datum geparst wird — alles in
# core/morgen.py. Kein HTTP, kein Backend: der Messenger muss reden können,
# BEVOR ZENTRALE wach ist (genau das ist sein Daseinsgrund).
#
# Start (normal über scripts/morgen_start.sh, das Fenster+Größe regelt):
#   python3 scripts/morgen_messenger.py
#   python3 scripts/morgen_messenger.py --force     # auch wenn nichts fällig ist
#   python3 scripts/morgen_messenger.py --selftest  # headless, ohne Terminal

import os
import sys
import time
import curses
from datetime import datetime, date

# core/ auffindbar machen, egal von wo gestartet (wie map_window.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'core'))

import morgen  # noqa: E402  (core/morgen.py — die ganze Logik)

MIN_H, MIN_W = 14, 46
# Feste Kastenmaße (in Zeichen, nach oben durch das Terminal begrenzt). Bewusst
# NICHT nach Inhalt wachsend: der Kasten steht bei jedem Schritt gleich da,
# statt bei jeder Antwort zu zappeln.
BOX_W, BOX_H = 56, 13

# Kein de_DE auf der Maschine (locale -a kennt nur en_US), strftime('%a') gäbe
# also 'sun' mitten in einer deutschen Oberfläche. Wochentage deshalb fest —
# genauso wie es Kalender und TUI halten (_WEEKDAYS_SHORT_DE / KAL_WD).
WOCHENTAGE = ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so']

# ── Farben ───────────────────────────────────────────────────────────────
# Dieselben zwei Themes wie die TUI (night/day), auf die paar Rollen
# eingedampft, die dieses Fenster wirklich braucht. Der Modus kommt aus
# ~/.config/zentrale/theme — derselben Datei, an der Terminal, Browser und
# nvim hängen. So sitzt der Messenger nicht als Fremdkörper auf dem Schirm.
THEMES = {
    'night': {'bg': 16,
              'acc': (108, 0), 'warn': (226, curses.A_BOLD), 'num': (222, 0),
              'ink': (231, 0), 'faint': (245, 0), 'bright': (231, curses.A_BOLD)},
    'day':   {'bg': 231,
              'acc': (65, 0), 'warn': (124, curses.A_BOLD), 'num': (26, 0),
              'ink': (16, 0), 'faint': (67, 0), 'bright': (16, curses.A_BOLD)},
}
THEME_FILE = os.path.expanduser('~/.config/zentrale/theme')


def resolved_theme():
    """day/night — exakt die Regel der TUI: Modus aus der Theme-Datei, 'auto'
    heißt hell zwischen 05:00 und 21:00."""
    mode = 'auto'
    try:
        with open(THEME_FILE, 'r', encoding='utf-8') as f:
            mode = (f.read().strip() or 'auto')
    except OSError:
        pass
    if mode in ('day', 'night'):
        return mode
    return 'day' if 5 <= int(time.strftime('%H')) < 21 else 'night'


class Screen:
    """Dünne Hülle um curses: Farben, ein zentrierter Kasten, geclippte Zeilen.
    Alles hier drin ist Darstellung — keine Entscheidung über Inhalte."""

    def __init__(self, stdscr):
        self.s = stdscr
        self.C = {}
        self._init_colors()

    def _init_colors(self):
        roles = ('acc', 'warn', 'num', 'ink', 'faint', 'bright')
        try:
            curses.start_color()
            curses.use_default_colors()
            has = curses.has_colors() and curses.COLORS >= 256
        except curses.error:
            has = False
        if not has:
            # Ohne 256 Farben bleibt nur Attribut-Kontrast — lesbar ist das
            # allemal, und der Messenger soll auf JEDEM Terminal aufgehen.
            self.C = {r: 0 for r in roles}
            self.C['bright'] = curses.A_BOLD
            self.C['faint'] = curses.A_DIM
            self.C['acc'] = curses.A_BOLD
            return
        t = THEMES[resolved_theme()]
        for i, r in enumerate(roles, start=1):
            fg, extra = t[r]
            curses.init_pair(i, fg, t['bg'])
            self.C[r] = curses.color_pair(i) | extra
        self.s.bkgd(' ', self.C['ink'])

    def put(self, y, x, text, attr=0):
        """Text schreiben, am Rand abgeschnitten. curses wirft am letzten
        Zeichen der letzten Zeile — das fangen wir stumm ab."""
        h, w = self.s.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        try:
            self.s.addstr(y, x, text[:max(0, w - x - 1)], attr)
        except curses.error:
            pass

    def box(self, y, x, h, w, title):
        if h < 2 or w < 2:
            return
        self.put(y, x, '┌' + '─' * (w - 2) + '┐', self.C['faint'])
        for i in range(1, h - 1):
            self.put(y + i, x, '│', self.C['faint'])
            self.put(y + i, x + w - 1, '│', self.C['faint'])
        self.put(y + h - 1, x, '└' + '─' * (w - 2) + '┘', self.C['faint'])
        if title:
            self.put(y, x + 2, ' ' + title.upper() + ' ', self.C['acc'])


def wrap(text, width):
    """Wortweiser Umbruch. Ein Wort, das allein nicht passt, wird hart
    getrennt — Aufgabentexte sind manchmal eine einzige lange URL."""
    words, lines, cur = (text or '').split(), [], ''
    for word in words:
        while len(word) > width:
            if cur:
                lines.append(cur); cur = ''
            lines.append(word[:width]); word = word[width:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += ' ' + word
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines or ['']


class Messenger:
    """
    Der Ablauf als kleiner Zustandsautomat. Zustände:

        schlaf_von → schlaf_bis → aufgabe ⇄ uebernommen → bestaetigen
                                     ↓ (später)
                              vertagen_datum → vertagen_zeit → aufgabe
    """

    def __init__(self, screen, force=False):
        self.sc = screen
        self.msg = ''                   # einzeilige Rückmeldung unter dem Inhalt
        self.buf = ''                   # aktuelles Eingabefeld
        self.von = ''                   # gemerkte Einschlafzeit (Anzeige)
        self.datum = ''                 # Rohtext des Vertagungs-Datums
        self.skipped = set()            # in DIESER Sitzung übergangene Aufgaben
        self.task = None
        self.done = False
        self.state = 'schlaf_von' if (force or morgen.sleep_open()) else 'aufgabe'
        if self.state == 'aufgabe':
            self._next_task()

    # ── Inhalt je Zustand: (Titel, Zeilen, Tastenzeile) ──────────────────

    def view(self):
        st = self.state
        if st == 'schlaf_von':
            return ('schlaf', ['wann bist du eingeschlafen?', '',
                               '  ' + self._field()],
                    'enter weiter · s überspringen · esc zu')
        if st == 'schlaf_bis':
            return ('schlaf', ['eingeschlafen  ' + self.von,
                               'wann bist du aufgewacht?', '',
                               '  ' + self._field()],
                    'enter eintragen · esc zurück')
        if st == 'aufgabe':
            if not self.task:
                return ('morgen', ['keine offene aufgabe.', 'schöner tag.'],
                        'enter zu')
            return ('aufgabe', wrap(self.task['text'], self._inner()) + ['', 'übernehmen?'],
                    'enter ja · l später · n nächste · esc zu')
        if st == 'uebernommen':
            return ('aufgabe', wrap(self.task['text'], self._inner())
                    + ['', '▸ übernommen'],
                    'enter erledigt · l später · n nächste · esc zu')
        if st == 'bestaetigen':
            return ('erledigt?', wrap(self.task['text'], self._inner())
                    + ['', 'wirklich erledigt?'],
                    'y ja · n nein')
        if st == 'vertagen_datum':
            return ('später', wrap(self.task['text'], self._inner())
                    + ['', 'an welchem tag?', '  ' + self._field(),
                       '  leer = heute'],
                    'enter weiter · esc zurück')
        if st == 'vertagen_zeit':
            return ('später', wrap(self.task['text'], self._inner())
                    + ['', 'um wie viel uhr?', '  ' + self._field()],
                    'enter vertagen · esc zurück')
        return ('morgen', ['bis später.'], 'enter zu')

    def _field(self):
        return (self.buf or '') + '▌'

    def _inner(self):
        """Textbreite im Kasten — danach richtet sich der Umbruch."""
        _, w = self.sc.s.getmaxyx()
        return max(10, min(w - 2, BOX_W) - 6)

    # ── Tasten ──────────────────────────────────────────────────────────

    def key(self, ch):
        enter = ch in (10, 13, curses.KEY_ENTER)
        backsp = ch in (curses.KEY_BACKSPACE, 127, 8)
        st = self.state
        self.msg = ''

        if st == 'schlaf_von':
            if ch == 27:
                return self._close()
            if ch in (ord('s'), ord('S')) and not self.buf:
                morgen.skip_sleep()
                self.state = 'aufgabe'; self._next_task(); return
            if enter:
                if morgen._parse_hhmm(self.buf) is None:
                    self.msg = 'zeit? HH:MM'
                else:
                    self.von = morgen.fmt_clock(morgen._parse_hhmm(self.buf))
                    self.state = 'schlaf_bis'; self.buf = ''
                return
            return self._edit(ch, backsp, clock=True)

        if st == 'schlaf_bis':
            if ch == 27:
                self.state = 'schlaf_von'; self.buf = ''; return
            if enter:
                bis = morgen._parse_hhmm(self.buf)
                if bis is None:
                    self.msg = 'zeit? HH:MM'
                    return
                von = morgen._parse_hhmm(self.von)
                morgen.log_sleep(von, bis)
                dauer = morgen.sleep_duration(von, bis)
                self.msg = 'eingetragen: %s–%s (%dh%02d)' % (
                    self.von, morgen.fmt_clock(bis), dauer // 60, dauer % 60)
                self.state = 'aufgabe'; self.buf = ''; self._next_task()
                return
            return self._edit(ch, backsp, clock=True)

        if st == 'aufgabe':
            if ch == 27 or not self.task:
                return self._close()
            if enter:
                morgen.take_on(self.task['key'])
                self.task['taken'] = True
                self.state = 'uebernommen'; return
            if ch in (ord('l'), ord('L')):
                self.state = 'vertagen_datum'; self.buf = ''; return
            if ch in (ord('n'), ord('N')):
                self.skipped.add(self.task['key']); self._next_task(); return
            return

        if st == 'uebernommen':
            if ch == 27:
                return self._close()
            if enter:
                self.state = 'bestaetigen'; return
            if ch in (ord('l'), ord('L')):
                self.state = 'vertagen_datum'; self.buf = ''; return
            if ch in (ord('n'), ord('N')):
                self.skipped.add(self.task['key'])
                self.state = 'aufgabe'; self._next_task(); return
            return

        if st == 'bestaetigen':
            if ch in (ord('y'), ord('Y'), ord('j'), ord('J')):
                morgen.conclude(self.task['lid'], self.task['iid'])
                self.msg = 'erledigt: ' + self.task['text']
                self.state = 'aufgabe'; self._next_task(); return
            if ch in (ord('n'), ord('N'), 27):
                self.state = 'uebernommen'; return
            return

        if st == 'vertagen_datum':
            if ch == 27:
                self.state = 'uebernommen' if self.task['taken'] else 'aufgabe'
                self.buf = ''; return
            if enter:
                # Datum erst zusammen mit der Uhrzeit prüfen — allein ist es
                # noch kein Zeitpunkt. Gemerkt wird der Rohtext.
                self.datum = self.buf; self.buf = ''
                self.state = 'vertagen_zeit'; return
            return self._edit(ch, backsp, date_chars=True)

        if st == 'vertagen_zeit':
            if ch == 27:
                self.buf = self.datum
                self.state = 'vertagen_datum'; return
            if enter:
                when = morgen.parse_when(self.datum, self.buf)
                if when is None:
                    self.msg = 'datum/zeit? z.b. 14:30'
                    return
                morgen.snooze(self.task['key'], when)
                morgen.drop(self.task['key'])
                self.msg = 'vertagt auf ' + when.strftime('%d.%m. %H:%M')
                self.buf = ''; self.state = 'aufgabe'; self._next_task()
                return
            return self._edit(ch, backsp, clock=True)

        if enter or ch == 27:
            self.done = True

    def _edit(self, ch, backsp, clock=False, date_chars=False):
        if backsp:
            self.buf = self.buf[:-1]
            return
        if ch < 32 or ch > 126:
            return
        c = chr(ch)
        ok = c.isdigit() or (clock and c == ':') or (date_chars and c in '.-/')
        limit = 10 if date_chars else 5
        if ok and len(self.buf) < limit:
            self.buf += c

    def _next_task(self):
        self.task = morgen.next_task(skip=self.skipped)
        self.state = 'uebernommen' if (self.task and self.task['taken']) else 'aufgabe'
        if not self.task:
            self.state = 'aufgabe'

    def _close(self):
        morgen.close_day()
        self.done = True

    # ── Zeichnen ────────────────────────────────────────────────────────

    def draw(self):
        s = self.sc
        H, W = s.s.getmaxyx()
        s.s.erase()
        if H < MIN_H or W < MIN_W:
            s.put(0, 0, 'fenster zu klein (min %dx%d)' % (MIN_W, MIN_H), s.C['warn'])
            s.s.refresh()
            return
        title, lines, keys = self.view()
        body = list(lines)
        w, h = min(W - 2, BOX_W), min(H - 2, BOX_H)
        y, x = max(0, (H - h) // 2), max(0, (W - w) // 2)
        s.box(y, x, h, w, title)

        # Kopfzeile: die Marke, wie in der TUI — ZEN invers, TRALE in Akzent.
        s.put(y + 1, x + 2, 'ZEN', s.C['bright'] | curses.A_REVERSE)
        s.put(y + 1, x + 5, 'TRALE', s.C['acc'])
        now = datetime.now()
        stamp = '%s %s' % (WOCHENTAGE[now.weekday()], now.strftime('%d.%m. · %H:%M'))
        s.put(y + 1, x + w - 2 - len(stamp), stamp, s.C['faint'])

        # Rückmeldung sitzt fest auf der vorletzten Zeile über den Tasten —
        # so schiebt sie den Inhalt darüber nicht hin und her.
        if self.msg:
            s.put(y + h - 3, x + 3, self.msg[:w - 6], s.C['num'])

        for i, line in enumerate(body[:h - 6]):
            attr = s.C['ink']
            if line.startswith('▸'):
                attr = s.C['acc']
            elif line.endswith('?'):
                attr = s.C['bright']
            s.put(y + 3 + i, x + 3, line[:w - 6], attr)

        s.put(y + h - 2, x + 3, keys[:w - 6], s.C['faint'])
        s.s.refresh()


def run(stdscr, force=False):
    curses.curs_set(0)
    stdscr.keypad(True)
    m = Messenger(Screen(stdscr), force=force)
    while not m.done:
        m.draw()
        ch = stdscr.getch()
        if ch == -1:
            continue
        if ch == curses.KEY_RESIZE:
            continue
        m.key(ch)
    return 0


def selftest():
    """Headless-Check ohne Terminal: Umbruch, Zeit-/Datums-Parser und der
    Zustandsautomat auf Papier. Läuft in der Test-Suite (tests/test_morgen.py)
    und per --selftest von Hand."""
    assert wrap('kurz', 20) == ['kurz']
    assert wrap('ein zwei drei', 8) == ['ein zwei', 'drei']
    assert wrap('abcdefghij', 4) == ['abcd', 'efgh', 'ij']
    assert morgen._parse_hhmm('2315') == 23 * 60 + 15
    assert morgen._parse_hhmm('7') == 420
    assert morgen._parse_hhmm('25:00') is None
    assert morgen.parse_when('', '14:30', today=date(2026, 8, 2)) \
        == datetime(2026, 8, 2, 14, 30)
    assert morgen.sleep_duration(23 * 60, 7 * 60) == 8 * 60
    print('morgen_messenger selftest ok')
    return 0


def main():
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    force = '--force' in sys.argv
    if not force and not morgen.is_due():
        # Nichts zu sagen → gar nicht erst ein Fenster aufreißen. Der Watcher
        # ruft uns lieber einmal zu viel auf als einmal zu wenig.
        sys.exit(0)
    if not sys.stdout.isatty():
        sys.stderr.write('morgen_messenger braucht ein echtes Terminal (TTY).\n')
        sys.exit(2)
    import locale
    locale.setlocale(locale.LC_ALL, '')
    sys.exit(curses.wrapper(run, force=force))


if __name__ == '__main__':
    main()
