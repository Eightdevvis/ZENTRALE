"""
Die Rückfrage im Kalender bricht lange Fragen um (16.10.2026).

Die Kollisions-Rückfrage ist ~120 Zeichen lang; der einzeilige Kasten
schnitt sie ab. Jetzt wächst der Kasten in der Höhe, Breite höchstens bw-4,
und jedes Wort der Frage steht auf dem Schirm.
"""
from tui.ansichten import kalender_bedienung as kbd

FRAGE = ("⚠ Teil-Überlappung: Probe (18:30-19:30) und Geigenstunde (18:00-19:00) "
         "@ Geigenschule überschneiden sich — trotzdem eintragen? (j/n): _")


class _Z:
    C = {"dim": 0, "bright": 1, "acc": 2, "faint": 3, "warn": 4}

    def __init__(self):
        self.text = []

    def safe_addstr(self, *a):
        pass

    def draw_box(self, *a):
        pass

    def addclip(self, y, x, s, w, attr):
        assert len(s) <= w
        self.text.append((y, s))


class _Frage:
    titel = "Kollision"

    def zeile(self):
        return FRAGE


def test_umbruch_verliert_nichts():
    zeilen = kbd.rueckfrage_zeilen(FRAGE, 40)
    assert len(zeilen) > 1 and all(len(z) <= 40 for z in zeilen)
    assert " ".join(zeilen).split() == FRAGE.split()


def test_kasten_zeigt_die_ganze_frage():
    b = object.__new__(kbd.Bedienung)
    b.z = _Z()
    b.W = {"dialog": _Frage()}
    b.zeichne_kasten(0, 0, 30, 60)          # Breite 60 → Kasten höchstens 56
    zeilen = [s for _y, s in sorted(b.z.text)]
    assert len(zeilen) >= 3
    assert " ".join(zeilen).split() == FRAGE.split()


def test_kurze_frage_bleibt_einzeilig():
    assert kbd.rueckfrage_zeilen("Löschen? (j/n)", 40) == ["Löschen? (j/n)"]
