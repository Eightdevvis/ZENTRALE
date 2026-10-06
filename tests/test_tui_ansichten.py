"""Die TUI ist seit 06.10.2026 in Ansichten geschnitten (tui/ansichten/,
memory/system/tui_bauplan.md). Was dabei nicht still kaputtgehen darf:

  1. Hot Reload sieht auch die Dateien im Unterordner — sonst lädt ein Merge,
     der nur eine Ansicht ändert, nicht neu.
  2. Der Aussenposten (Pi) bekommt alles, was zentrale_tui.py importiert —
     er hat eine Positivliste, und was fehlt, lässt die TUI dort nicht starten.
  3. Keine Ansicht importiert zentrale_tui: als Skript gestartet heißt die
     Datei __main__, ein Import lüde sie ein zweites Mal mit eigenem
     RELOAD/ENDE/RAD — Hot Reload und /quit liefen ins Leere.
  4. Die Zeichen-Primitive des Kontexts verhalten sich wie vorher.
"""
import ast
import os

from tui import zentrale_tui as zt
from tui.ansichten import kontext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUI = os.path.join(ROOT, "tui")


def test_hot_reload_sieht_unterordner(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "ansichten").mkdir()
    (tmp_path / "ansichten" / "b.py").write_text("y = 1\n")
    (tmp_path / "ansichten" / "__pycache__").mkdir()
    (tmp_path / "ansichten" / "__pycache__" / "c.py").write_text("")
    (tmp_path / "notiz.txt").write_text("")
    namen = [os.path.relpath(p, tmp_path) for p in zt.code_dateien(str(tmp_path))]
    assert namen == ["a.py", os.path.join("ansichten", "b.py")]


def test_hot_reload_ohne_ordner_ist_leer(tmp_path):
    assert zt.code_dateien(str(tmp_path / "gibtsnicht")) == []


def _positivliste():
    with open(os.path.join(ROOT, "deploy", "aussenposten.txt"), encoding="utf-8") as f:
        return [z.strip() for z in f if z.strip() and not z.lstrip().startswith("#")]


def test_aussenposten_bekommt_alle_tui_teile():
    liste = _positivliste()

    def drin(rel):
        return any(rel == e or (e.endswith("/") and rel.startswith(e)) for e in liste)

    fehlt = []
    for wurzel, unter, namen in os.walk(TUI):
        unter[:] = [d for d in unter if d != "__pycache__"]
        for n in namen:
            if n.endswith(".py"):
                rel = os.path.relpath(os.path.join(wurzel, n), ROOT).replace(os.sep, "/")
                if not drin(rel):
                    fehlt.append(rel)
    assert not fehlt, ("Nicht in deploy/aussenposten.txt — auf dem Pi fehlt das, "
                       "und die TUI startet dort nicht: %s" % fehlt)


def test_keine_ansicht_importiert_zentrale_tui():
    ordner = os.path.join(TUI, "ansichten")
    schuldig = []
    for n in sorted(os.listdir(ordner)):
        if not n.endswith(".py"):
            continue
        baum = ast.parse(open(os.path.join(ordner, n), encoding="utf-8").read())
        for k in ast.walk(baum):
            namen = []
            if isinstance(k, ast.Import):
                namen = [a.name for a in k.names]
            elif isinstance(k, ast.ImportFrom):
                namen = [k.module or ""] + [a.name for a in k.names]
            if any("zentrale_tui" in x for x in namen):
                schuldig.append(n)
    assert not schuldig, "Ansichten importieren zentrale_tui: %s" % schuldig


class _Schirm:
    """Ein stdscr, das nur mitschreibt."""

    def __init__(self, h=10, w=20):
        self.h, self.w, self.raus = h, w, []

    def getmaxyx(self):
        return self.h, self.w

    def addstr(self, y, x, text, attr=0):
        self.raus.append((y, x, text, attr))


def _kontext(schirm):
    return kontext.Kontext(schirm, store=None, has_color=False, theme_state=None)


def test_safe_addstr_schneidet_am_rand_und_ersetzt_nullbytes():
    s = _Schirm(h=5, w=10)
    z = _kontext(s)
    z.safe_addstr(1, 6, "abcdef\x00")
    z.safe_addstr(1, -2, "xyz")
    z.safe_addstr(9, 0, "weg")              # unter dem Rand: nichts
    z.safe_addstr(2, 3, 42)                  # keine Zeichenkette: zu str
    assert s.raus == [(1, 6, "abcd", 0), (1, 0, "z", 0), (2, 3, "42", 0)]


def test_addclip_kuerzt_und_streicht_durch():
    s = _Schirm(h=5, w=40)
    z = _kontext(s)
    z.addclip(0, 0, "langer text", 5)
    z.addclip(1, 0, "ab", 5, strike=True)
    z.addclip(2, 0, "nie", 0)
    assert s.raus == [(0, 0, "lange", 0), (1, 0, "a̶b̶", 0)]


def test_draw_box_zeichnet_rahmen_und_titel():
    s = _Schirm(h=10, w=40)
    z = _kontext(s)
    z.C.update(faint=1, acc=2)
    z.draw_box(0, 0, 3, 6, "ab")
    assert s.raus[0] == (0, 0, "┌────┐", 1)
    assert s.raus[-1] == (0, 2, " AB ", 2)
    assert (2, 0, "└────┘", 1) in s.raus


def test_projekt_wurzel_stimmt():
    from tui.ansichten import basis
    assert basis.PROJEKT == ROOT
    assert zt.PROJEKT == ROOT


def test_ansichten_rechnen_pfade_nie_vom_eigenen_file():
    """Eine Closure, die aus run_ui in tui/ansichten/ umzieht, liegt eine
    Ebene tiefer: dirname(dirname(__file__)) zeigt dann auf tui/ statt aufs
    Projekt, und das Karten-Fenster oder der Ton fänden ihre Skripte nicht
    mehr. Deshalb gibt es genau EINE Stelle, die rechnet: basis.PROJEKT."""
    ordner = os.path.join(TUI, "ansichten")
    schuldig = [n for n in sorted(os.listdir(ordner))
                if n.endswith(".py") and n != "basis.py"
                and "__file__" in open(os.path.join(ordner, n), encoding="utf-8").read()]
    assert not schuldig, "eigene Pfad-Rechnung statt basis.PROJEKT: %s" % schuldig
