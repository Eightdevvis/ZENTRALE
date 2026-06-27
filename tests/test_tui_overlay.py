"""Das Befehls-Overlay muss DECKEND sein.

Curses kennt keine Z-Order/Opazität: der stdout-Bereich ist schon gezeichnet,
wenn das Overlay drüberkommt. Früher schrieb das Overlay nur seine echten
Zeichen — wo eine Zeile kürzer war als die Kasten-Innenbreite, blieb der
darunterliegende stdout stehen und „blutete" in den Kasten. `render_overlay_body`
putzt jetzt jede Zeile zuerst über die volle Innenbreite.

Getestet wird die ECHTE Render-Funktion gegen einen Fake-Screen, der jede Zelle
mitschreibt — so ist das ein Bild-Test, kein Logik-Abklatsch.
"""
from tui.zentrale_tui import overlay_rows, render_overlay_body

STDOUT_CH = "X"   # simuliert bereits gezeichneten stdout-Text unter dem Overlay


class FakeScreen:
    """Minimaler Zell-Puffer mit denselben zwei Primitiven wie der curses-
    Adapter in run_ui: fill() blankt, put() schreibt auf maxw gekürzt."""
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.cells = [[STDOUT_CH] * w for _ in range(h)]

    def _stamp(self, y, x, s):
        if not (0 <= y < self.h):
            return
        for ch in s:
            if 0 <= x < self.w:
                self.cells[y][x] = ch
            x += 1

    def fill(self, y, x, n, ch, attr=0):
        self._stamp(y, x, ch * max(0, n))

    def put(self, y, x, text, maxw, attr=0):
        if maxw <= 0:
            return
        self._stamp(y, x, str(text)[:maxw])

    def row(self, y):
        return "".join(self.cells[y])


def _layout(W, n_rows):
    """Dieselbe Geometrie wie run_ui."""
    ov_w = min(W - 4, 56)
    ov_x = 2
    ov_y = 1
    return ov_x, ov_y, ov_w


ATTRS = {"acc": 0, "num": 0, "dim": 0, "faint": 0}


def test_overlay_interior_is_opaque():
    """Keine stdout-Zelle überlebt im Kasten-Inneren — über ALLE Zeilentypen."""
    W = 100
    _, rows = overlay_rows("/", False, None)      # echte cmd-Zeilen
    ov_x, ov_y, ov_w = _layout(W, len(rows))
    scr = FakeScreen(len(rows) + ov_y + 2, W)
    render_overlay_body(scr, rows, ov_x, ov_y, ov_w, ATTRS)

    lo, hi = ov_x + 1, ov_x + ov_w - 2           # Innenbreite (zwischen den Rändern)
    for i in range(len(rows)):
        yy = ov_y + 1 + i
        bled = [x for x in range(lo, hi + 1) if scr.cells[yy][x] == STDOUT_CH]
        assert not bled, (
            "stdout blutet in Overlay-Zeile %d, Spalten %s:\n%r"
            % (i, bled, scr.row(yy)))


def test_overlay_actually_draws_content():
    """Gegenprobe: der Test ist nicht leer — Befehlsnamen landen wirklich im Bild."""
    W = 100
    _, rows = overlay_rows("/help", True, None)
    ov_x, ov_y, ov_w = _layout(W, len(rows))
    scr = FakeScreen(len(rows) + ov_y + 2, W)
    render_overlay_body(scr, rows, ov_x, ov_y, ov_w, ATTRS)

    painted = "\n".join(scr.row(ov_y + 1 + i) for i in range(len(rows)))
    cmd_names = [r[1] for r in rows if r[0] == "cmd"]
    assert cmd_names, "erwarte cmd-Zeilen in /help"
    for name in cmd_names:
        assert name in painted, "Befehl %r fehlt im gerenderten Overlay" % name


def test_overlay_opaque_even_when_content_short():
    """Der eigentliche Bug: kurze Zeile + langer stdout darunter. Die
    Rest-Innenbreite rechts vom Text MUSS Leerzeichen sein, kein stdout."""
    W = 100
    # eine künstliche, sehr kurze info-Zeile erzwingt viel Rest-Breite
    rows = [("info", "", "x")]
    ov_x, ov_y, ov_w = _layout(W, len(rows))
    scr = FakeScreen(ov_y + 3, W)
    render_overlay_body(scr, rows, ov_x, ov_y, ov_w, ATTRS)

    yy = ov_y + 1
    interior = "".join(scr.cells[yy][ov_x + 1: ov_x + ov_w - 1])
    assert STDOUT_CH not in interior, \
        "kurze Zeile lässt stdout durchscheinen: %r" % scr.row(yy)
    assert "x" in interior, "Inhalt der kurzen Zeile fehlt"
