"""Gesprächsliste und Gesprächs-Befehle der TUI ohne Bildschirm
(tui/ansichten/gespraechsliste.py, chat_gespraeche.py — Phase 2, 2026-10-07)."""
import curses
import types
from datetime import datetime, timedelta, timezone

import pytest

from tui.ansichten import chat as chatmod
from tui.ansichten import chat_befehle, chat_gespraeche, gespraechsliste
from tui.ansichten.gespraechsliste import alter_text, filtern, listen_zeilen

JETZT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _vor(**k):
    return (JETZT - timedelta(**k)).isoformat()


@pytest.mark.parametrize("vorher,text", [
    (dict(seconds=10), "gerade"), (dict(minutes=5), "vor 5 Min."),
    (dict(hours=2, minutes=10), "vor 2 Std."), (dict(hours=30), "gestern"),
    (dict(days=3), "vor 3 Tagen"), (dict(days=40), "28.08."),
])
def test_alter_text(vorher, text):
    assert alter_text(_vor(**vorher), JETZT) == text


def test_alter_text_mit_muell():
    assert alter_text(None, JETZT) == "" and alter_text("gestern", JETZT) == ""


def test_filtern_nach_allen_woertern_im_titel():
    e = [{"titel": "Fahrrad Schlauch flicken"}, {"titel": "Steuer"}, {"titel": None}]
    assert filtern(e, "schlauch FAHR") == [e[0]]
    assert filtern(e, "") == e


def test_listen_zeilen_zeiger_punkt_alter_und_kuerzen():
    e = [{"id": "erinnerungen", "titel": "Erinnerungen", "letzte": _vor(minutes=5),
          "ungelesen": True},
         {"id": "a", "titel": "Ein sehr langer Titel, der nicht in die Zeile passt",
          "letzte": _vor(hours=2)}]
    z = listen_zeilen(e, 1, 30, JETZT, aktiv="a")
    assert z[0] == ("  ● Erinnerungen    vor 5 Min.", "ungelesen")
    assert z[1][0].startswith("› · Ein sehr") and z[1][0].endswith("vor 2 Std.")
    assert "…" in z[1][0] and len(z[1][0]) <= 30 and z[1][1] == "gewaehlt"


# ── Die Überlagerung mit gefälschtem Backend ──────────────────────────

class FakeChat:
    def __init__(self):
        self.AI = {"streaming": False, "msg": "", "gid": "a", "liste": None}
        self.z = None
        self.geoeffnet, self.titel, self.neu, self.geleert = [], [], 0, 0

    def gespraech_oeffnen(self, gid):
        self.geoeffnet.append(gid)

    def titel_setzen(self, gid, titel):
        self.titel.append((gid, titel))

    def neues_gespraech(self):
        self.neu += 1

    def leeren(self):
        self.geleert += 1

    def markiert(self, eintraege):
        return list(eintraege)


@pytest.fixture
def backend(monkeypatch):
    daten = {"liste": [
        {"id": "erinnerungen", "titel": "Erinnerungen", "letzte": _vor(minutes=1), "ungelesen": True},
        {"id": "a", "titel": "Fahrrad", "letzte": _vor(minutes=5)},
        {"id": "b", "titel": "Steuer", "letzte": _vor(days=2)}],
        "archiv": [{"id": "c", "titel": "Alt", "letzte": _vor(days=30), "archiviert": True}],
        "aufrufe": []}

    def api(pfad, methode="GET", body=None, timeout=3.0):
        daten["aufrufe"].append((methode, pfad, body))
        if pfad.startswith("/api/gespraeche") and methode == "GET":
            return {"aktiv": "a", "gespraeche": daten["archiv" if "archiv=1" in pfad else "liste"]}
        return {"ok": True}
    monkeypatch.setattr(gespraechsliste, "api_call", api)
    return daten


def _tippe(liste, *tasten):
    for t in tasten:
        liste.taste(ord(t) if isinstance(t, str) else t)


def test_oeffnen_steht_auf_dem_offenen_gespraech(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    assert c.AI["liste"]["idx"] == 1 and l.gewaehlt()["id"] == "a"


def test_waehlen_und_oeffnen(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    _tippe(l, curses.KEY_DOWN, 10)
    assert c.geoeffnet == ["b"] and c.AI["liste"] is None


def test_filtern_mit_schraegstrich(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    _tippe(l, "/", "s", "t", "e", 10)
    assert [e["id"] for e in l.sichtbar()] == ["b"]
    assert not c.AI["liste"]["suchen"]
    _tippe(l, "n")                          # nach der Suche wieder ein Befehl
    assert c.neu == 1


def test_umbenennen(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    _tippe(l, "r", 127, 127, 127, 127, 127, 127, 127, "R", "a", "d", 10)
    assert c.titel == [("a", "Rad")]


def test_erinnerungen_wird_weder_umbenannt_noch_archiviert(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    _tippe(l, curses.KEY_UP, "r")
    assert c.AI["liste"]["umbenennen"] is None and "namen" in c.AI["msg"]
    _tippe(l, "a")
    assert not any(m == "POST" for m, _p, _b in backend["aufrufe"])


def test_archivieren_und_archiv_zeigen(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    l.oeffnen()
    _tippe(l, "a")                          # das offene Gespräch „a"
    assert ("POST", "/api/gespraeche/a/archiv", {"an": True}) in backend["aufrufe"]
    assert c.geleert == 1 and "archiviert" in c.AI["msg"]
    _tippe(l, "z")
    assert c.AI["liste"]["archiv"] and l.gewaehlt()["id"] == "c"
    _tippe(l, "a")
    assert ("POST", "/api/gespraeche/c/archiv", {"an": False}) in backend["aufrufe"]


def test_esc_und_tab_schliessen(backend):
    c = FakeChat()
    l = gespraechsliste.Gespraechsliste(c)
    for taste in (27, 9):
        l.oeffnen()
        l.taste(taste)
        assert c.AI["liste"] is None


def test_waehrend_einer_antwort_geht_die_liste_auf(backend):
    """Seit 2026-10-09 (wie Claude Web): die Antwort läuft im Hintergrund
    weiter, Sasha darf die Gespräche sehen und wechseln (chat_strom.py)."""
    c = FakeChat()
    c.AI["streaming"] = True
    gespraechsliste.Gespraechsliste(c).oeffnen()
    assert c.AI["liste"] is not None and c.AI["liste"]["eintraege"]


# ── Verlauf, Denken, Titel, Befehle ───────────────────────────────────

def test_verlauf_aus_mit_denken_und_werkzeugen():
    h = [{"role": "user", "content": "frage"},
         {"role": "assistant", "content": "antwort", "denken": "hm",
          "werkzeuge": [{"name": "read_note", "args": "name=x"},
                        {"name": "web", "args": "", "fehler": True, "ergebnis": "kaputt"},
                        {"name": "read_time", "args": "", "ergebnis": "12:00"}]}]
    # Seit 2026-10-07 mit gekürztem Ergebnis, damit „Used … ›" es aufklappt.
    assert chat_gespraeche.verlauf_aus(h) == [
        ("user", "frage"), ("denken", "hm"), ("werkzeug", "read_note(name=x)"),
        ("werkzeug", "web()"), ("werkzeug_fehler", "web ✗ kaputt"),
        ("werkzeug", "read_time()"), ("werkzeug_ergebnis", "↳ 12:00"), ("ai", "antwort")]


def test_denken_eingeklappt_eine_zeile_aufgeklappt_alles():
    zu = chatmod.denken_wrap("x" * 1234, False, 40)
    assert zu == [("denken", "  ▸ gedacht (1 234 Zeichen)")]
    auf = chatmod.denken_wrap("ein gedanke", True, 40)
    assert auf[0][1].strip().startswith("▾ gedacht") and len(auf) >= 2


def _chat_attrappe(**ai):
    c = chatmod.Chat.__new__(chatmod.Chat)
    import threading
    c.AI = {"backend": "cloud", "model": "m", "provider": "claude", "kosten_heute": 0.5,
            "budget": {}, "neu": False, "titel": "", **ai}
    c.AI_LOCK = threading.Lock()
    return c


def test_kastentitel_zeigt_gespraechstitel_und_kuerzt_ihn():
    c = _chat_attrappe(titel="Fahrradschlauch flicken unterwegs")
    voll = c.ai_titel(200)
    assert voll == "ki-chat · Fahrradschlauch flicken unterwegs · cloud (claude) · 0,50€ heute"
    eng = c.ai_titel(50)
    assert len(eng) <= 50 and "cloud (claude)" in eng and "…" in eng
    assert c.ai_titel(30).startswith("ki-chat")      # zu eng: Titel fällt weg


def test_neue_befehle_sind_bekannt():
    for b in ("liste", "titel", "archiv", "wiederholen", "bearbeiten", "denken"):
        assert chat_befehle.lesen("/" + b).art == "befehl"
    assert chat_befehle.lesen("/titel Mein Rad").arg == "Mein Rad"
    assert "/retry" in chat_befehle.hilfe_text()
