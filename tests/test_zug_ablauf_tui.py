"""„trace ›" unter einer Antwort (tui/ansichten/spur.py, 2026-10-09): wer es
bekommt, Aufklappen holt das Protokoll, jeder Eintrag erst als Kopfzeile,
per Klick ganz; /trace legt es in die Ablage. Erfundene Inhalte."""
import curses
import time

import pytest

from test_chat_web_teile import Schirm, Theme, _klick, _zeichnen   # noqa: F401
from tui.ansichten import chat as chatmod, chat_befehle, kontext, spur, verlauf as V

VERLAUF = [{"id": "n1", "role": "user", "content": "hab ich dienstag zahnarzt?"},
           {"id": "n2", "role": "assistant", "content": "Alte Antwort ohne Protokoll."},
           {"id": "n3", "role": "user", "content": "und mittwoch?"},
           {"id": "n4", "role": "assistant", "content": "Mittwoch ist frei.", "ablauf_n": 5}]
ABLAUF = [
    {"art": "system", "t": 0.0, "fingerabdruck": "abc123", "laenge": 18000},
    {"art": "kontext", "t": 0.0, "text": "<kontext_automatisch>\n## Jetzt\nMontag\n</kontext_automatisch>"},
    {"art": "werkzeug", "t": 1.0, "name": "read_calendar", "args": {"tag": "mittwoch"},
     "ergebnis": "[ergebnis: ok]\n" + "\n".join("Zeile %d vom Kalender" % i for i in range(30)),
     "status": "ok", "dauer": 0.2},
    {"art": "antwort", "t": 2.0, "text": "Mittwoch ist frei."},
    {"art": "kosten", "t": 2.0, "runden": 2, "eingabe": 200, "ausgabe": 40,
     "cache_lesen": 180, "cache_schreiben": 0, "euro": 0.0012}]


# ── Reine Funktionen ─────────────────────────────────────────────────────

def test_nur_antworten_mit_protokoll_bekommen_trace():
    log = [("user", "a"), ("ai", "Alte Antwort ohne Protokoll."), ("user", "b"),
           ("werkzeug", "read_calendar()"), ("ai", "Mittwoch ist frei.")]
    s = spur.spuren(log, VERLAUF)
    assert s == {4: "n4"}
    zeilen = V.verlauf_zeilen(log, 80, spuren=s)
    texte = ["".join(t for t, _s, _z in z) for z in zeilen]
    assert sum("trace ›" in t for t in texte) == 1
    assert ("trace", 4) in V.ziele(zeilen)
    # alte Gespräche ohne Protokoll: gar kein trace
    assert not any("trace" in t for t in
                   ("".join(x for x, _s, _z in z) for z in V.verlauf_zeilen(log, 80)))


@pytest.mark.parametrize("breite", [20, 80, 136])
def test_aufgeklappt_kopfzeilen_dann_ganz(breite):
    log = [("user", "b"), ("ai", "Mittwoch ist frei.")]
    s, a = {1: "n4"}, {"n4": ABLAUF}
    offen = {("trace", 1)}
    zeilen = V.verlauf_zeilen(log, breite, offen=offen, spuren=s, ablaeufe=a)
    texte = ["".join(t for t, _s, _z in z) for z in zeilen]
    assert all(len(t) <= breite for t in texte)
    if breite >= 80:
        assert any("tool read_calendar · ok · 0.2 s" in t for t in texte)
        assert any("cost · 2 round(s)" in t for t in texte)
    assert not any("Zeile 29 vom Kalender" in t for t in texte)        # erst nur Kopf
    offen.add(("spur", (1, 2)))
    zeilen = V.verlauf_zeilen(log, breite, offen=offen, spuren=s, ablaeufe=a)
    texte = ["".join(t for t, _s, _z in z) for z in zeilen]
    assert all(len(t) <= breite for t in texte)
    ganz = "\n".join(texte)
    if breite >= 80:
        assert "Zeile 0 vom Kalender" in ganz and "Zeile 29 vom Kalender" in ganz
        assert "[ergebnis: ok]" in ganz and '"tag": "mittwoch"' in ganz


def test_laedt_und_fehler():
    log = [("ai", "x")]
    z = V.verlauf_zeilen(log, 80, offen={("trace", 0)}, spuren={0: "n"},
                         ablaeufe={"n": spur.LAEDT})
    assert any("loading" in t for t, _s, _z in sum(z, []))
    z = V.verlauf_zeilen(log, 80, offen={("trace", 0)}, spuren={0: "n"},
                         ablaeufe={"n": "no trace stored for this answer"})
    assert any("no trace stored" in t for t, _s, _z in sum(z, []))


def test_befehl_trace_gibt_es():
    e = chat_befehle.lesen("/trace")
    assert (e.art, e.name) == ("befehl", "trace")
    assert "/trace" in chat_befehle.hilfe_text()


# ── Im Chat: Klick, Tastatur, /trace ─────────────────────────────────────

@pytest.fixture
def welt(monkeypatch):
    aufrufe = []

    def api(pfad, methode="GET", body=None, timeout=3.0, **_k):
        aufrufe.append((methode, pfad))
        if pfad.startswith("/api/chat/history"):
            return list(VERLAUF)
        if pfad.startswith("/api/rueckmeldungen"):
            return {"rueckmeldungen": []}
        if pfad == "/api/gespraeche/g1/ablauf/n4":
            return {"gespraech": "g1", "nachricht": "n4", "ablauf": ABLAUF}
        if pfad == "/api/gespraeche/g1/ablauf/letzte/ablage":
            return {"ok": True, "dokument": {"id": "d9", "titel": "Ablauf: Zahnarzt",
                                             "art": "text", "fassung": 1}}
        return {}
    from tui import ansichten as A
    for name in dir(A):
        m = getattr(A, name)
        if hasattr(m, "api_call"):
            monkeypatch.setattr(m, "api_call", api)

    def bauen(h=30, w=136):
        z = kontext.Kontext(Schirm(h, w), None, False, Theme())
        z.apply_theme("night")
        c = chatmod.Chat(z)
        c.AI["active"] = True
        c.AI["gid"], c.AI["titel"] = "g1", "Zahnarzt"
        c.AI["log"] = [("user", "hab ich dienstag zahnarzt?"), ("ai", "Alte Antwort ohne Protokoll."),
                       ("user", "und mittwoch?"), ("ai", "Mittwoch ist frei.")]
        c.AI["spuren"] = spur.spuren(c.AI["log"], VERLAUF)
        c.bewertung.geladen("g1", VERLAUF)
        c.aufrufe = aufrufe
        aufrufe.clear()
        return c
    return bauen


def _warten(c, nid):
    for _ in range(100):
        if isinstance(c.AI.get("ablaeufe", {}).get(nid), list):
            return
        time.sleep(0.01)
    raise AssertionError("protokoll nicht geholt")


def _schirm(c):
    return "\n".join(c.z.stdscr.zeile(y) for y in range(c.z.stdscr.h))


@pytest.mark.parametrize("groesse", [(24, 80), (30, 136)])
def test_klick_auf_trace_holt_und_zeigt(welt, monkeypatch, groesse):
    c = welt(*groesse)
    _zeichnen(c)
    assert _schirm(c).count("trace ›") == 1
    _klick(c, monkeypatch, "trace ›")
    _warten(c, "n4")
    assert ("GET", "/api/gespraeche/g1/ablauf/n4") in c.aufrufe
    _zeichnen(c)
    s = _schirm(c)
    assert "trace ⌄" in s and "tool read_calendar" in s
    _klick(c, monkeypatch, "tool read_calendar")
    _zeichnen(c)
    assert ("spur", (3, 2)) in c.AI["offen"]
    # noch einmal: wieder zu, ohne neu zu holen
    n = len(c.aufrufe)
    c.ziel_ausloesen(("trace", 3))
    c.ziel_ausloesen(("trace", 3))
    assert len(c.aufrufe) == n
    _zeichnen(c)


def test_tastatur_wie_bisher(welt):
    c = welt()
    _zeichnen(c)
    c.fokus_weiter()                       # F6: Verlauf, letztes Ziel
    c.AI["fokus"] = "verlauf"
    c.AI["vwahl"] = ("trace", 3)
    c.taste(10)                            # Enter klappt auf
    _warten(c, "n4")
    _zeichnen(c)
    c.taste(curses.KEY_DOWN)
    c.taste(curses.KEY_DOWN)
    c.taste(curses.KEY_DOWN)               # gut, schlecht, erster Eintrag
    assert c.AI["vwahl"][0] == "spur"
    c.taste(10)
    _zeichnen(c)
    assert c.AI["vwahl"] in c.AI["offen"]


def test_slash_trace_legt_ab(welt):
    c = welt()
    c.befehl("trace", "")
    assert ("POST", "/api/gespraeche/g1/ablauf/letzte/ablage") in c.aufrufe
    assert "ablage" in c.AI["msg"] and any(r == "ablage" for r, _t in c.AI["log"])
