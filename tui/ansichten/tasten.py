# tui/ansichten/tasten.py
#
# Die Tastentabelle in der TUI: EINE Tabelle je Programm, aus der die
# Tastenverteilung UND die Leiste ganz unten lesen (Sasha, 2026-10-11:
# „die shortcuts sind gehardcoded und fliegen deswegen so komisch rum").
# Form und Beschriftungen: core/tastentabelle.py (neutral, auch für app.toml).
#
# Ein Programm, das mitmacht:
#
#     class Notizen:
#         TASTEN = Tasten({
#             "liste": [("↑↓", "waehlen", "select"), ("k", "waehlen"),
#                       ("enter", "oeffnen", "open"), ("esc", "zu", "back")],
#             "frage": [("j/enter", "ja", "yes"), ("any key", "nein", "cancel")],
#         })
#         def ansicht(self):            # welche Ansicht ist gerade offen?
#             return "frage" if self.NOTE["confirm"] else "liste"
#         def taste(self, ch):          # die Hauptschleife ruft das
#             return self.TASTEN.verteilen(self, self.ansicht(), ch)
#         def aktion_waehlen(self, taste):   # taste = neutraler Name: "up", "k" …
#             ...
#
# Eine Aktion bekommt den neutralen Tastennamen („up", „a", „alt+left",
# „enter"); bei „type" (Freitext) das Zeichen selbst (Leertaste = " ").
# Ihr Rückgabewert geht an die Hauptschleife (BEENDEN beendet).
#
# Kurzform der Einträge: (taste, aktion) oder (taste, aktion, text) — ohne
# Text verarbeitet, aber nicht angezeigt. TASTEN.daten() ist die neutrale
# Form (Liste von Objekten), wie sie im app.toml steht.
#
# Der Horcher (horcher.py) sammelt beim Verkabeln die Einträge jeder
# Ansicht ein; die Leiste fragt nur noch ihn.

import curses

from .basis import kern_pfad

kern_pfad()
import tastentabelle as tt  # noqa: E402  – core/tastentabelle.py, stdlib-only

FREITEXT, JEDE = tt.FREITEXT, tt.JEDE

_CURSES = {
    curses.KEY_UP: "up", curses.KEY_DOWN: "down",
    curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
    curses.KEY_BTAB: "shift+tab", curses.KEY_BACKSPACE: "backspace",
    127: "backspace", 8: "backspace", curses.KEY_DC: "del",
    curses.KEY_HOME: "home", curses.KEY_END: "end",
    curses.KEY_PPAGE: "pgup", curses.KEY_NPAGE: "pgdn",
    10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
    9: "tab", 32: "space", 27: "esc",
    # Shift+Pfeil, wie curses es übersetzt (Desk: Ausschnitt schieben)
    curses.KEY_SR: "shift+up", curses.KEY_SF: "shift+down",
    curses.KEY_SLEFT: "shift+left", curses.KEY_SRIGHT: "shift+right",
}
_CURSES.update({curses.KEY_F0 + i: "f%d" % i for i in range(1, 13)})
_NAME_ZU_CODE = {"up": curses.KEY_UP, "down": curses.KEY_DOWN,
                 "left": curses.KEY_LEFT, "right": curses.KEY_RIGHT,
                 "shift+tab": curses.KEY_BTAB, "backspace": curses.KEY_BACKSPACE,
                 "del": curses.KEY_DC, "home": curses.KEY_HOME, "end": curses.KEY_END,
                 "pgup": curses.KEY_PPAGE, "pgdn": curses.KEY_NPAGE,
                 "enter": 10, "tab": 9, "space": 32, "esc": 27,
                 "shift+up": curses.KEY_SR, "shift+down": curses.KEY_SF,
                 "shift+left": curses.KEY_SLEFT, "shift+right": curses.KEY_SRIGHT}
_NAME_ZU_CODE.update({"f%d" % i: curses.KEY_F0 + i for i in range(1, 13)})
# Alt+Pfeil als EIN Keycode (terminfo kUP3 …, Modifier 3 = Alt)
_ALT_KEYNAME = {b"kUP3": "alt+up", b"kDN3": "alt+down",
                b"kLFT3": "alt+left", b"kRIT3": "alt+right",
                # Shift+Pfeil als eigener Keycode (Modifier 2), wie der Desk
                # sie vor 2026-10-11 selbst kannte
                b"kUP2": "shift+up", b"kDN2": "shift+down",
                b"kLFT2": "shift+left", b"kRIT2": "shift+right"}
# Roh durchgereichtes Shift+Pfeil (xterm: ESC [ 1 ; 2 A …)
_SHIFT_FOLGE = (("[1;2A", "up"), ("[1;2B", "down"), ("[1;2C", "right"), ("[1;2D", "left"))
_PFEIL_FOLGE = (("[1;3A", "up"), ("[1;3B", "down"), ("[1;3C", "right"),
                ("[1;3D", "left"), ("[A", "up"), ("[B", "down"), ("[C", "right"),
                ("[D", "left"), ("OA", "up"), ("OB", "down"), ("OC", "right"),
                ("OD", "left"))


def codes(name):
    """Neutraler Tastenname → Tastencodes, die ein Terminal dafür schickt
    (die erste Form; für Tests und den Horcher)."""
    if name.startswith("alt+"):
        rest = name[4:]
        return [27, _NAME_ZU_CODE.get(rest, 13 if rest == "enter" else None) or ord(rest)]
    if name.startswith("ctrl+"):
        return [ord(name[5]) - 96]
    if name in _NAME_ZU_CODE:
        return [_NAME_ZU_CODE[name]]
    return [ord(name)]


def _esc_folge(stdscr):
    """Nach einem Esc: kommt gleich mehr (Alt-Taste)? → 'alt+…' oder 'esc'.
    Wartet höchstens 50 ms auf das erste Folgebyte (wie früher die Karte)."""
    seq = []
    try:
        stdscr.timeout(50)
        first = stdscr.getch()
        if first != -1:
            seq.append(first)
            stdscr.nodelay(True)
            for _ in range(7):
                nx = stdscr.getch()
                if nx == -1:
                    break
                seq.append(nx)
        stdscr.timeout(250)
    except curses.error:
        pass
    if not seq:
        return "esc"
    for n in seq:                              # Meta=Esc + übersetzter Pfeil
        if n in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            return "alt+" + _CURSES[n]
    if len(seq) == 1 and seq[0] in (10, 13, curses.KEY_ENTER):
        return "alt+enter"
    if len(seq) == 1 and 33 <= seq[0] <= 126:
        return "alt+" + chr(seq[0])
    s = "".join(chr(n) for n in seq if 0 <= n < 256).lstrip("\x1b")
    for k, v in _SHIFT_FOLGE:
        if s.startswith(k):
            return "shift+" + v
    for k, v in _PFEIL_FOLGE:
        if s.startswith(k):
            return "alt+" + v
    return None                                # unbekannte Folge: verwerfen


def name_von(ch, stdscr=None, alt=False):
    """Tastencode → neutraler Name (oder None). alt=True: nach Esc kurz auf
    eine Alt-Folge horchen — nur Ansichten mit alt+-Tasten zahlen die 50 ms."""
    if ch is None or ch == -1:
        return None
    try:
        kn = curses.keyname(ch)
    except Exception:
        kn = b""
    if kn in _ALT_KEYNAME:
        return _ALT_KEYNAME[kn]
    if ch == 27:
        return _esc_folge(stdscr) if (alt and stdscr is not None) else "esc"
    if ch in _CURSES:
        return _CURSES[ch]
    if 1 <= ch <= 26:
        return "ctrl+" + chr(ch + 96)
    if 33 <= ch <= 126:                        # wie bisher: druckbares ASCII
        return chr(ch)                         # (≥256 sind curses-Tasten wie KEY_RESIZE)
    return None


def _als_objekt(e):
    if isinstance(e, dict):
        return dict(e)
    o = {"taste": e[0], "aktion": e[1]}
    if len(e) > 2 and e[2]:
        o["text"] = e[2]
    return o


class Tasten:
    """Eine Tastentabelle: zeigt (eintraege) und verteilt (verteilen)."""

    @classmethod
    def zusammen(cls, eigene, teile):
        """Tabelle eines Programms, das Teile mit eigener Tabelle hat (Chat mit
        Gesprächsliste/Gedächtnis …, Desk mit Farbwähler-Modal …).
        eigene = Tabelle wie bei Tasten(…); teile = {name: (Tasten, weg)} mit
        weg(programm) → das Objekt, das die aktion_-Methoden des Teils hat.
        Die Ansichten eines Teils heißen „name:ansicht"."""
        tab = dict(eigene)
        ziele = {}
        for name, (teil, weg) in teile.items():
            for a, liste in teil._daten.items():
                tab[name + ":" + a] = [dict(e) for e in liste]
                ziele[name + ":" + a] = weg
        t = cls(tab)
        t._ziele = ziele
        return t

    def ziel(self, programm, ansicht):
        """Wessen aktion_-Methoden in dieser Ansicht gelten."""
        weg = self._ziele.get(ansicht)
        return weg(programm) if weg else programm

    def fehlende_methoden(self, programm):
        """[(ansicht, aktion)] ohne Methode am Ziel (ein Test verlangt [])."""
        return [(a, e["aktion"]) for a, liste in self._daten.items() for e in liste
                if not callable(getattr(self.ziel(programm, a), "aktion_" + e["aktion"], None))]

    def __init__(self, tabelle):
        self._ziele = {}
        daten = {a: [_als_objekt(e) for e in liste] for a, liste in tabelle.items()}
        fehler = tt.pruefen(daten)
        if fehler:
            raise ValueError("tastentabelle: " + "; ".join(fehler))
        self._daten = daten
        self._karte, self._frei, self._jede, self._alt = {}, {}, {}, {}
        for ansicht, liste in daten.items():
            karte = self._karte[ansicht] = {}
            for e in liste:
                if e["taste"] == FREITEXT:
                    self._frei[ansicht] = e["aktion"]
                elif e["taste"] == JEDE:
                    self._jede[ansicht] = e["aktion"]
                else:
                    for n in tt.namen(e["taste"]):
                        karte.setdefault(n, e["aktion"])
            self._alt[ansicht] = any(n.startswith("alt+") for n in karte)

    def daten(self):
        """Die neutrale Form (core/tastentabelle.py) — eine Kopie."""
        return {a: [dict(e) for e in liste] for a, liste in self._daten.items()}

    def ansichten(self):
        return list(self._daten)

    def eintraege(self, ansicht):
        """[(taste, text)], was die Leiste in dieser Ansicht zeigt."""
        return tt.eintraege(self._daten, ansicht)

    def aktionen(self):
        """Alle Aktionsnamen (ein Test verlangt zu jeder eine Methode)."""
        return {e["aktion"] for liste in self._daten.values() for e in liste}

    def freitext(self, ansicht):
        """Nimmt die Ansicht Freitext? Dann ist '/' dort ein Zeichen."""
        return ansicht in self._frei

    def nimmt(self, ansicht, name):
        """Aktion für den neutralen Tastennamen in der Ansicht, sonst None."""
        if ansicht not in self._daten or name is None:
            return None
        a = self._karte[ansicht].get(name)
        if a is None and ansicht in self._frei and (len(name) == 1 or name == "space"):
            a = self._frei[ansicht]
        if a is None:
            a = self._jede.get(ansicht)
        return a

    def verteilen(self, programm, ansicht, ch):
        """Taste ch an die Aktion des Programms, die sie in `ansicht` hat.
        Nicht belegt → nichts passiert (None)."""
        stdscr = getattr(getattr(programm, "z", None), "stdscr", None)
        name = name_von(ch, stdscr, alt=self._alt.get(ansicht, False))
        aktion = self.nimmt(ansicht, name)
        if aktion is None:
            return None
        if aktion == self._frei.get(ansicht) and (len(name) == 1 or name == "space") \
                and self._karte[ansicht].get(name) is None:
            name = " " if name == "space" else name
        return getattr(self.ziel(programm, ansicht), "aktion_" + aktion)(name)
