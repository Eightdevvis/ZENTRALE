"""Chat nach dem Vorbild von Claude Web (2026-10-07): Seitenleiste, Maus,
Zwischenablage, Einstellungen, rechte Seite — und der ganze Chat ohne
Bildschirm gezeichnet und geklickt."""
import curses
import datetime as _dt

import pytest

from tui.ansichten import (chat as chatmod, chat_bedienung, einstellungen, kontext, maus,
                           rechts, seitenleiste, symbole)


def test_gruppen_today_yesterday_datum():
    jetzt = _dt.datetime(2026, 10, 7, 12, 0, tzinfo=_dt.timezone.utc)
    assert seitenleiste.gruppe("2026-10-07T08:00:00+00:00", jetzt) == "Today"
    assert seitenleiste.gruppe("2026-10-06T08:00:00+00:00", jetzt) == "Yesterday"
    assert seitenleiste.gruppe("2026-10-03T08:00:00+00:00", jetzt) == "Oct 3"
    assert seitenleiste.gruppe("2025-10-03T08:00:00+00:00", jetzt) == "Oct 3 2025"
    assert seitenleiste.gruppe("quatsch", jetzt) == "Older"


def test_leisten_zeilen_punkt_blatt_projekt_und_kuerzen():
    jetzt = _dt.datetime(2026, 10, 7, 12, 0, tzinfo=_dt.timezone.utc)
    e = [{"id": "a", "titel": "Erinnerungen", "letzte": "2026-10-07T09:00:00+00:00",
          "ungelesen": True},
         {"id": "b", "titel": "Ein sehr langer Titel über Fahrradschläuche", "projekt_name": "Rad",
          "letzte": "2026-10-07T08:00:00+00:00"},
         {"id": "c", "titel": "Steuer", "letzte": "2026-10-01T08:00:00+00:00"}]
    z = seitenleiste.zeilen(e, 26, jetzt, mit_doku={"b"})
    assert [a for a, _i, _t in z] == ["kopf", "chat", "chat", "luft", "kopf", "chat"]
    assert z[1][2].startswith("● Erinnerungen")
    assert z[2][2].startswith("  Rad · Ein") and z[2][2].endswith(" " + symbole.DOKU)
    assert all(len(t) <= 26 for _a, _i, t in z)


def test_maus_deuten_und_treffen():
    assert maus.deuten(curses.BUTTON1_CLICKED) == "klick"
    assert maus.deuten(curses.BUTTON1_DOUBLE_CLICKED) == "doppel"
    assert maus.deuten(curses.BUTTON4_PRESSED) == "rad_hoch"
    assert maus.deuten(maus.RAD_RUNTER) == "rad_runter"
    assert maus.deuten(curses.BUTTON1_RELEASED) is None
    a, b = object(), object()
    f = [(3, 0, 10, a), (3, 5, 8, b)]
    assert maus.treffer(f, 3, 6) is b and maus.treffer(f, 3, 2) is a
    assert maus.treffer(f, 4, 6) is None
    assert maus.rad_treffer([(0, 0, 10, 20, "verlauf")], 5, 5) == "verlauf"
    assert maus.gewuenscht({}) and not maus.gewuenscht({"ZENTRALE_TUI_MAUS": "aus"})


def test_zwischenablage_je_nach_umgebung():
    def da(n):
        return "/usr/bin/" + n

    def weg(n):
        return None
    assert chat_bedienung.zwischenablage({"WAYLAND_DISPLAY": "w"}, da) == ["wl-copy"]
    assert chat_bedienung.zwischenablage({"DISPLAY": ":0"}, da)[0] == "xclip"
    assert chat_bedienung.zwischenablage({"DISPLAY": ":0"}, weg) is None
    assert chat_bedienung.zwischenablage({}, da) is None   # SSH/Kiosk ohne X


def test_einstellungen_helfer():
    g = einstellungen.gruppiert([{"name": "web_search"}, {"name": "read_calendar"},
                                 {"name": "neu_unbekannt"}, {"name": "read_note"}])
    assert [x for x, _l in g] == ["Calendar", "Memory", "Web", "Other"]
    assert einstellungen.balken(0.5, 10) == "▰" * 5 + "▱" * 5
    assert einstellungen.balken(7, 4) == "▰▰▰▰" and einstellungen.balken(None, 2) == "▱▱"
    s = einstellungen.skill_zeilen({"name": "x", "status": "aus", "herkunft": "anthropic",
                                    "beschreibung": "tut was", "braucht": "einen browser"}, 40)
    texte = [t for t, _a in s]
    assert "[ off ○]" in texte and "by Anthropic" in texte and "Needs" in texte
    k = einstellungen.kosten_zeilen({"heute": 0.1, "monat": 2, "calls_heute": 3,
                                     "geschaetzt_monat": 0.5,
                                     "budget": {"limit": 20, "anteil": 0.1, "status": "ok"},
                                     "modelle": {"m": 2}}, 60)
    texte = [t for t, _a in k]
    assert any("estimated" in t for t in texte) and any("▰" in t for t in texte)
    assert einstellungen.kosten_zeilen({}, 40)[-1][0].startswith("no monthly budget")


def test_rechts_dokumente_und_vorschau():
    log = [("ablage", "d1\tA"), ("ai", "x"), ("ablage", "d2\tB"), ("ablage", "d1\tA")]
    assert rechts.dokumente(log) == [("d1", "A"), ("d2", "B")]
    dok = {"kopf": {"art": "markdown"}, "inhalt": "# Titel\n\n- eins\n- zwei\n- drei"}
    assert rechts.vorschau_zeilen(dok, 30) == ["Titel", "• eins", "• zwei"]


# ── Der ganze Chat ohne Bildschirm ────────────────────────────────────

class Schirm:
    def __init__(self, h, w):
        self.h, self.w, self.text = h, w, {}

    def getmaxyx(self):
        return (self.h, self.w)

    def addstr(self, y, x, s, attr=0):
        for i, c in enumerate(s):
            self.text[(y, x + i)] = c

    def zeile(self, y):
        return "".join(self.text.get((y, x), " ") for x in range(self.w))

    def __getattr__(self, name):
        return lambda *a, **k: -1


class Theme:
    def __getattr__(self, name):
        return lambda *a, **k: "night"


DOK = {"kopf": {"id": "d1", "titel": "Packliste", "art": "markdown", "fassung": 2},
       "fassung": 2, "inhalt": "# Packliste\n\n" + "\n".join("- ding %d" % i for i in range(40))}
GESPRAECHE = {"aktiv": "g1", "gespraeche": [
    {"id": "g1", "titel": "Schlauch", "letzte": "2026-10-07T08:00:00+00:00"},
    {"id": "g2", "titel": "Steuer", "letzte": "2026-10-01T08:00:00+00:00"}]}


@pytest.fixture
def welt(monkeypatch):
    aufrufe = []

    def api(pfad, methode="GET", body=None, timeout=3.0, **_k):
        aufrufe.append((methode, pfad, body))
        if pfad.startswith("/api/ablage/"):
            return DOK
        if pfad.startswith("/api/ablage"):
            return {"dokumente": [{"id": "d1", "gespraech": "g1"}]}
        if pfad.startswith("/api/gespraeche"):
            return GESPRAECHE
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
        c.AI["gespraeche"] = GESPRAECHE["gespraeche"]
        c.AI["gid"], c.AI["titel"] = "g1", "Schlauch"
        c.AI["log"] = [("user", "wie flicke ich?"), ("werkzeug", "read_note(name=rad)"),
                       ("werkzeug_ergebnis", "↳ flickzeug"), ("ablage", "d1\tPackliste"),
                       ("ai", "Mit Flickzeug.")]
        c.aufrufe = aufrufe
        return c
    return bauen


def _zeichnen(c):
    h, w = c.z.stdscr.getmaxyx()
    c.z.stdscr.text.clear()
    c.draw_ai(2, 0, h - 6, w)


def _klick(c, monkeypatch, text):
    """Auf das erste Vorkommen von text klicken."""
    s = c.z.stdscr
    for y in range(s.h):
        x = s.zeile(y).find(text)
        if x >= 0:
            monkeypatch.setattr(curses, "getmouse", lambda: (0, x, y, 0, curses.BUTTON1_CLICKED))
            c.taste(curses.KEY_MOUSE)
            return
    raise AssertionError("nicht auf dem schirm: %r" % text)


@pytest.mark.parametrize("groesse", [(24, 80), (30, 136), (45, 160), (14, 60)])
def test_zeichnen_in_allen_groessen(welt, groesse):
    c = welt(*groesse)
    for vorbereiten in (lambda: None, lambda: c.seite.aufklappen(),
                        lambda: c.rechts.outputs_umschalten(),
                        lambda: c.rechts.dokument_zeigen("d1"),
                        lambda: c.einstellungen.oeffnen("capabilities")):
        vorbereiten()
        _zeichnen(c)
    assert c.klicks


def test_klick_klappt_schritt_auf_und_oeffnet_dokument(welt, monkeypatch):
    c = welt()
    _zeichnen(c)
    _klick(c, monkeypatch, "Used memory ›")
    assert ("schritt", 1) in c.AI["offen"]
    _zeichnen(c)
    assert any("→ flickzeug" in c.z.stdscr.zeile(y) for y in range(30))
    _klick(c, monkeypatch, "▤ Packliste ›")
    assert c.rechts.art() == "dokument" and c.AI["fokus"] == "rechts"
    _zeichnen(c)
    _klick(c, monkeypatch, "×")                       # schließen
    assert c.rechts.art() is None and c.AI["fokus"] == "eingabe"


def test_klick_in_der_seitenleiste_oeffnet_gespraech(welt, monkeypatch):
    c = welt()                                         # 136 breit: Leiste von selbst offen
    _zeichnen(c)
    _klick(c, monkeypatch, "Steuer")
    assert ("POST", "/api/gespraeche/aktiv", {"id": "g2"}) in c.aufrufe
    _klick(c, monkeypatch, "Customize")
    assert c.AI["einstellungen"]


def test_tab_klappt_auf_und_zu_f6_wechselt_den_fokus(welt):
    c = welt(24, 80)
    _zeichnen(c)
    assert not c._seite_sichtbar()                     # 80 breit: zu
    c.taste(9)
    _zeichnen(c)
    assert c._seite_sichtbar() and c.AI["fokus"] == "seite"
    c.taste(9)
    _zeichnen(c)
    assert not c._seite_sichtbar() and c.AI["fokus"] == "eingabe"
    c.taste(curses.KEY_F6)
    assert c.AI["fokus"] in ("verlauf", "eingabe") and c.AI["fokus"] != "seite"


def test_verlauf_mit_tasten(welt):
    c = welt()
    _zeichnen(c)
    c.AI["fokus"] = "verlauf"
    c.taste(curses.KEY_UP)                             # vom Ende: das letzte Ziel
    assert c.AI["vwahl"] == ("wiederholen", 4)
    c.taste(curses.KEY_UP)
    c.taste(curses.KEY_UP)
    c.taste(curses.KEY_UP)
    assert c.AI["vwahl"] == ("schritt", 1)
    c.taste(10)
    assert ("schritt", 1) in c.AI["offen"]
    c.taste(27)
    assert c.AI["fokus"] == "eingabe"


def test_kopieren_ohne_zwischenablage_sagt_wo_der_text_liegt(welt, monkeypatch, tmp_path):
    c = welt()
    monkeypatch.setattr(chat_bedienung, "zwischenablage", lambda: None)
    monkeypatch.setattr(chat_bedienung.tempfile, "gettempdir", lambda: str(tmp_path))
    c.ziel_ausloesen(("kopieren", 4))
    assert (tmp_path / "zentrale-kopie.txt").read_text() == "Mit Flickzeug."
    assert "keine zwischenablage" in c.AI["msg"]


def test_strg_tasten(welt):
    c = welt()
    c.taste(15)                                        # Strg+O: Outputs
    assert c.rechts.art() == "outputs"
    c.taste(21)                                        # Strg+U: Anhang
    assert c.AI["input"] == "/attach "


def test_denk_adern_laufen_und_ziehen_sich_zurueck(welt, monkeypatch):
    c = welt()
    jetzt = [1000.0]
    monkeypatch.setattr(chatmod.time, "monotonic", lambda: jetzt[0])
    from tui.ansichten import chat_zeichnen
    monkeypatch.setattr(chat_zeichnen.time, "monotonic", lambda: jetzt[0])
    c.AI.update(streaming=True, answer="", denk_t0=990.0, denk_log_n=len(c.AI["log"]))
    assert c._adern_lage(True, "", 1000.0)[:2] == (True, 0.0)
    assert c._adern_lage(True, "", 1000.0)[2] == pytest.approx(10.0)
    an, aus, _d = c._adern_lage(True, "Antwort", 1000.0)      # erster Text: Rückzug
    assert an and aus == 0.0
    an, aus, _d = c._adern_lage(False, None, 1000.5)
    assert an and 0 < aus < 1
    assert c._adern_lage(False, None, 1002.0)[0] is False and not c.adern_laufen()
