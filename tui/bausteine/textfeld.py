# tui/bausteine/textfeld.py
#
# Ein kleiner mehrzeiliger Texteditor für Modale (zuerst: Notiz auf dem
# Desk bearbeiten, 2026-10-09). Enter = neue Zeile, Strg+S = speichern,
# Esc = abbrechen. Ohne curses-Zeichnen: `taste` ändert Text und Cursor,
# `anzeige` liefert die sichtbaren Zeilen samt Cursor — der Gastgeber malt.
#
# Warum nicht tui/ansichten/eingabe.py: das ist das Eingabefeld des Chats
# (Enter schickt ab, Alt+Enter/\-Enter für neue Zeilen, Grenze 20 000) und
# liegt in ansichten/ — ein Baustein soll nicht von einer Ansicht abhängen.
#
# Zeichen kommen als Bytes (getch, wie überall in der TUI); ein Umlaut kommt
# als zwei Bytes und wird hier zusammengesetzt.

import curses

ENTER = (10, 13, curses.KEY_ENTER)
ZURUECK = (curses.KEY_BACKSPACE, 127, 8)
STRG_S = 19
ESC = 27
GRENZE = 20000


class Textfeld:
    def __init__(self, text=""):
        self.text = str(text or "")
        self.pos = len(self.text)
        self._bytes = b""
        self._spalte = None              # gemerkte Spalte für ↑↓
        self._breite = 40                # letzte Anzeige-Breite (für ↑↓)
        self.oben = 0                    # erste sichtbare Zeile

    # ── Tasten ────────────────────────────────────────────────────────
    def taste(self, ch):
        """-> None | "speichern" | "abbrechen"."""
        if ch == STRG_S:
            return "speichern"
        if ch == ESC:
            return "abbrechen"
        if ch in (curses.KEY_UP, curses.KEY_DOWN):
            self._hoch_runter(-1 if ch == curses.KEY_UP else 1)
            return None
        self._spalte = None
        if ch in ENTER:
            self._einfuegen("\n")
        elif ch in ZURUECK:
            if self.pos > 0:
                self.text = self.text[:self.pos - 1] + self.text[self.pos:]
                self.pos -= 1
        elif ch == curses.KEY_DC:
            self.text = self.text[:self.pos] + self.text[self.pos + 1:]
        elif ch == curses.KEY_LEFT:
            self.pos = max(0, self.pos - 1)
        elif ch == curses.KEY_RIGHT:
            self.pos = min(len(self.text), self.pos + 1)
        elif ch == curses.KEY_HOME:
            self.pos = self.text.rfind("\n", 0, self.pos) + 1
        elif ch == curses.KEY_END:
            ende = self.text.find("\n", self.pos)
            self.pos = len(self.text) if ende < 0 else ende
        elif 32 <= ch < 127:
            self._einfuegen(chr(ch))
        elif 0x80 <= ch <= 0xFF:
            self._utf8(ch)
        return None

    def _einfuegen(self, s):
        if len(self.text) + len(s) > GRENZE:
            return
        self.text = self.text[:self.pos] + s + self.text[self.pos:]
        self.pos += len(s)

    def _utf8(self, byte):
        self._bytes += bytes([byte])
        try:
            zeichen = self._bytes.decode("utf-8")
        except UnicodeDecodeError:
            if len(self._bytes) >= 4:    # Müll: verwerfen statt ewig sammeln
                self._bytes = b""
            return
        self._bytes = b""
        self._einfuegen(zeichen)

    # ── Anzeige ───────────────────────────────────────────────────────
    def zeilen(self, breite):
        """Sichtbare Zeilen bei `breite`, hart umbrochen: [(start, text)]."""
        breite = max(1, breite)
        raus, start = [], 0
        for zeile in self.text.split("\n"):
            if not zeile:
                raus.append((start, ""))
            for i in range(0, len(zeile), breite):
                raus.append((start + i, zeile[i:i + breite]))
            if zeile and len(zeile) % breite == 0:
                raus.append((start + len(zeile), ""))   # Cursor am vollen Zeilenende
            start += len(zeile) + 1
        return raus

    def cursor(self, breite):
        """(zeile, spalte) des Cursors in zeilen(breite)."""
        reihen = self.zeilen(breite)
        for i, (start, text) in enumerate(reihen):
            letzte = i + 1 == len(reihen) or reihen[i + 1][0] != start + len(text)
            if start <= self.pos < start + len(text) or (letzte and self.pos == start + len(text)):
                return i, self.pos - start
        return len(reihen) - 1, 0

    def _hoch_runter(self, schritt):
        reihen = self.zeilen(self._breite)
        r, s = self.cursor(self._breite)
        if self._spalte is None:
            self._spalte = s
        ziel = r + schritt
        if 0 <= ziel < len(reihen):
            start, text = reihen[ziel]
            self.pos = start + min(self._spalte, len(text))

    def anzeige(self, breite, hoehe):
        """-> (zeilen als Text, (cursor_zeile, cursor_spalte)) für das
        sichtbare Fenster; scrollt so, dass der Cursor drin bleibt."""
        self._breite = max(1, breite)
        reihen = self.zeilen(breite)
        r, s = self.cursor(breite)
        hoehe = max(1, hoehe)
        if r < self.oben:
            self.oben = r
        elif r >= self.oben + hoehe:
            self.oben = r - hoehe + 1
        self.oben = max(0, min(self.oben, max(0, len(reihen) - hoehe)))
        sicht = [t for _s, t in reihen[self.oben:self.oben + hoehe]]
        return sicht, (r - self.oben, s)
