"""Werkzeug-Schritte im Chat: erst kurz, „… mehr" zeigt alles (2026-10-09).

Sasha: „ich würde gerne mehr von dem inneren zeug der ki lesen können" —
bis dahin hielt der Verlauf nur 300 Zeichen eines Ergebnisses und zeigte 3
Zeilen. Jetzt bleibt das Ergebnis (fast) ganz, die KI bekommt in ihrer
Werkzeug-Spur trotzdem nur den Anfang (sonst wird jeder Zug teurer)."""
import werkzeug_befund
from tui.ansichten import verlauf as V

LANG = " ".join("wort%d" % n for n in range(400))
LOG = [("user", "such mal"),
       ("werkzeug", "web_search(query=herbstferien saarland 2026)"),
       ("werkzeug_ergebnis", "↳ " + LANG),
       ("ai", "fertig")]


def _text(zeilen):
    return "\n".join("".join(t for t, _, _ in z) for z in zeilen)


def test_kurz_mit_mehr_knopf():
    t = _text(V.verlauf_zeilen(LOG, 60, offen={("schritt", 1)}))
    assert "… mehr (" in t
    assert "wort399" not in t


def test_mehr_zeigt_alles_und_weniger():
    z = V.verlauf_zeilen(LOG, 60, offen={("schritt", 1), ("voll", 1)})
    t = _text(z)
    assert "wort399" in t and "‹ weniger" in t
    assert ("voll", 1) in V.ziele(z)


def test_kurzes_ergebnis_ohne_mehr():
    log = LOG[:2] + [("werkzeug_ergebnis", "↳ kurz")] + LOG[3:]
    t = _text(V.verlauf_zeilen(log, 60, offen={("schritt", 1)}))
    assert "mehr" not in t


def test_spur_fuer_die_ki_bleibt_kurz():
    spur = werkzeug_befund.spur_zeile([{"name": "add_calendar_entry", "args": "x=1",
                                         "schreibt": True, "status": "ok",
                                         "ergebnis": LANG}])
    assert "wort399" not in spur
    assert len(spur) < werkzeug_befund.SPUR_ERGEBNIS_MAX + 200
