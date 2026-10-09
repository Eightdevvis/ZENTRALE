"""
Laufende Antwort im TUI-Chat (tui/ansichten/chat_strom.py, 2026-10-09):
„antwort läuft" bleibt nie stehen (äußeres finally, Wächter), und die
Antwort läuft im Hintergrund weiter, während Sasha andere Gespräche liest.
"""
import json
import threading
from types import SimpleNamespace

import pytest

from tui.ansichten import chat, chat_gespraeche, chat_strom


class _Schirm:
    def getch(self):
        return -1

    def timeout(self, ms):
        pass

    def nodelay(self, an):
        pass

    def getmaxyx(self):
        return (30, 136)


class _Strom:
    """Gefälschter SSE-Strom. Ein Eintrag ist ein Ereignis (dict) oder eine
    Funktion — die läuft genau an dieser Stelle (Sasha tut etwas, während
    die Antwort einläuft)."""

    def __init__(self, folge):
        self.folge = folge

    def __iter__(self):
        for e in self.folge:
            if callable(e):
                e()
                continue
            yield ("data: " + json.dumps(e) + "\n").encode()

    def close(self):
        pass


@pytest.fixture
def c(monkeypatch):
    ch = chat.Chat(SimpleNamespace(stdscr=_Schirm(), C={}))
    ch.AI.update(active=True, gid="a", titel="Stundenplan", loaded=True,
                 log=[("user", "alt"), ("ai", "alte antwort")])
    ch.geladen = []
    ch.verlauf_laden = lambda gid=None: ch.geladen.append(gid)   # kein Netz
    monkeypatch.setattr(chat_gespraeche, "api_call", lambda *a, **k: {})
    monkeypatch.setattr(chat_strom, "api_call", lambda *a, **k: {})
    return ch


def _laufen(c, monkeypatch, folge, frage="schau ins lsf"):
    """Wie senden(), nur dass der Strom hier im Test-Thread läuft."""
    monkeypatch.setattr(chat.urllib.request, "urlopen", lambda *a, **k: _Strom(folge))
    with monkeypatch.context() as m:
        m.setattr(chat.threading.Thread, "start", lambda self: None)
        c.senden(frage)
    c.ai_stream(frage)


def _warte_auf(bedingung):
    import time
    for _ in range(100):
        if bedingung():
            return
        time.sleep(0.01)
    assert bedingung()


# ── 1. „antwort läuft" bleibt nicht stehen ────────────────────────────

BROWSER_ZUG = [{"strom": "z7"}, {"gespraech": "a", "nachricht": "n1"},
               {"permission": {"frage": "Browser öffnen?", "optionen": ["ja", "nein"]}},
               {"werkzeug": {"phase": "start", "name": "browser_open", "args": {"url": "x"}}},
               {"werkzeug": {"phase": "fertig", "name": "browser_open", "text": "Seite"}},
               {"werkzeug": {"phase": "start", "name": "browser_click", "args": {"nr": 9}}},
               {"werkzeug": {"phase": "fertig", "name": "browser_click", "text": "Seite 2"}},
               {"token": "Bin rein."},
               {"ehrlichkeit": {"erledigt": [], "zeile": "", "offen": []}},
               {"antwort": "m9", "ablauf": 15}, {"done": True}]


def test_browser_zug_endet_sauber(c, monkeypatch):
    _laufen(c, monkeypatch, BROWSER_ZUG)
    assert not c.AI["streaming"] and c.AI["log"][-1] == ("ai", "Bin rein.")
    assert c.AI["spuren"][len(c.AI["log"]) - 1] == "m9"


def test_ausnahme_im_abschluss_laesst_nichts_haengen(c, monkeypatch):
    def kaputt(*a, **k):
        raise TypeError("kaputt")
    monkeypatch.setattr(chat, "pruefung_eintraege", kaputt)
    with pytest.raises(TypeError):
        _laufen(c, monkeypatch, BROWSER_ZUG)
    assert not c.AI["streaming"]
    assert "nicht ganz an" in c.AI["msg"]
    _warte_auf(lambda: c.geladen == ["a"])


def test_ausnahme_vor_dem_lesen_laesst_nichts_haengen(c, monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("urlopen kaputt")
    monkeypatch.setattr(chat.urllib.request, "urlopen", kaputt)
    with monkeypatch.context() as m:
        m.setattr(chat.threading.Thread, "start", lambda self: None)
        c.senden("frage")
    with pytest.raises(RuntimeError):
        c.ai_stream("frage")
    assert not c.AI["streaming"]


def test_kaputte_ereignisse_werden_uebergangen(c, monkeypatch):
    _laufen(c, monkeypatch, [{"werkzeug": "kein dict"}, {"ehrlichkeit": ["liste"]},
                             {"permission": "frage?"}, {"ablage": {"ohne": "id"}},
                             {"token": "ok"}, {"done": True}])
    assert not c.AI["streaming"] and c.AI["log"][-1] == ("ai", "ok")


def test_waechter_setzt_zurueck_wenn_kein_thread_mehr_lebt(c):
    t = threading.Thread(target=lambda: None)
    t.start(); t.join()
    c.AI.update(streaming=True, strom_thread=t, answer="halb", perm={"frage": "?"})
    assert c.waechter() is True
    assert not c.AI["streaming"] and c.AI["perm"] is None and c.AI["answer"] is None
    assert "zurückgesetzt" in c.AI["msg"]
    _warte_auf(lambda: c.geladen == ["a"])


def test_waechter_laesst_lebenden_oder_startenden_strom_in_ruhe(c):
    halt = threading.Event()
    t = threading.Thread(target=halt.wait)
    c.AI.update(streaming=True, strom_thread=t)
    assert c.waechter() is False                     # noch nicht gestartet
    t.start()
    try:
        assert c.waechter() is False and c.AI["streaming"]
    finally:
        halt.set(); t.join()
    assert c.waechter() is True


def test_waechter_ohne_strom_tut_nichts(c):
    assert c.waechter() is False and c.AI["msg"] == ""


# ── 2. Wechseln während einer Antwort ─────────────────────────────────

def test_antwort_landet_in_ihrem_gespraech_auch_wenn_sasha_wechselt(c, monkeypatch):
    gesehen = {}

    def weg():
        c.gespraech_oeffnen("b")
        c.AI["log"] = [("user", "steuerfrage")]       # was verlauf_laden brächte
        gesehen["woanders"] = c.markiert([{"id": "a"}, {"id": "b"}])

    def zurueck():
        c.gespraech_oeffnen("a")
        gesehen["zurueck"] = list(c.AI["log"])

    _laufen(c, monkeypatch, [{"strom": "z1"}, {"token": "Bin "}, weg,
                             {"werkzeug": {"phase": "start", "name": "browser_open",
                                           "args": {"url": "x"}}},
                             {"token": "rein."}, zurueck, {"done": True}])
    assert gesehen["woanders"][0]["laeuft"] and "laeuft" not in gesehen["woanders"][1]
    # zurück: der Stand von unterwegs ist da, live weiter
    assert ("werkzeug", "browser_open(url=x)") in gesehen["zurueck"]
    assert c.AI["gid"] == "a" and c.AI["log"][-1] == ("ai", "Bin rein.")
    assert ("user", "steuerfrage") not in c.AI["log"]
    assert not c.AI["streaming"]
    _warte_auf(lambda: c.geladen == ["b"])


def test_fertig_im_hintergrund_markiert_das_gespraech(c, monkeypatch):
    def weg():
        c.gespraech_oeffnen("b")
        c.AI["log"] = [("user", "steuerfrage")]
    posts = []
    monkeypatch.setattr(chat_gespraeche, "api_call", lambda *a, **k: posts.append(a) or {})
    monkeypatch.setattr(chat_strom, "api_call", lambda *a, **k: posts.append(a) or {})
    _laufen(c, monkeypatch, [{"token": "fertig"}, weg, {"done": True}])
    assert c.AI["log"] == [("user", "steuerfrage")]          # nichts hineingeschrieben
    assert not c.AI["streaming"] and "a" in c.AI["ungesehen"] and c.ungelesen()
    assert c.markiert([{"id": "a"}])[0]["ungelesen"]
    # Beim Backend erst jetzt gewechselt (vorher hätte das „für dieses
    # Gespräch" der laufenden Antwort aufgehoben).
    assert posts == [("/api/gespraeche/aktiv", "POST", {"id": "b"})]
    c.gespraech_oeffnen("a")
    assert "a" not in c.AI["ungesehen"]


def test_frage_im_hintergrund_wird_nicht_verschluckt(c, monkeypatch):
    gesehen = {}

    def weg():
        c.gespraech_oeffnen("b")
        c.AI["input"] = "neue frage"

    def schauen():
        gesehen["markiert"] = c.markiert([{"id": "a"}])
        gesehen["ungelesen"] = c.ungelesen()
        gesehen["perm_hier"] = c.AI["perm"]
        gesehen["fuss"] = c._fuss(None, None, "", "", False, "", 0, 80,
                                  (c.strom_titel(), bool(c.strom_woanders().get("perm"))))
        c.ai_submit()                                   # im anderen Chat senden
        gesehen["msg"], gesehen["input"] = c.AI["msg"], c.AI["input"]

    c.z.C = {"warn": 1, "faint": 2, "dim": 3}
    _laufen(c, monkeypatch, [weg, {"permission": {"frage": "Browser?", "optionen": ["ja"]}},
                             schauen, {"done": True}])
    assert gesehen["markiert"][0]["ungelesen"] and gesehen["ungelesen"]
    assert gesehen["perm_hier"] is None                 # j/n hier tippen antwortet nicht
    assert "Stundenplan" in gesehen["fuss"][0][0] and "fragt" in gesehen["fuss"][0][0]
    assert gesehen["msg"] == "warte, „Stundenplan“ antwortet noch"
    assert gesehen["input"] == "neue frage"             # bleibt stehen


def test_neues_gespraech_bleibt_gesperrt_mit_titel(c, monkeypatch):
    gesehen = {}

    def weg():
        c.gespraech_oeffnen("b")
        c.neues_gespraech()
        gesehen["msg"] = c.AI["msg"]
    _laufen(c, monkeypatch, [weg, {"done": True}])
    assert gesehen["msg"] == "warte, „Stundenplan“ antwortet noch"


def test_neues_gespraech_im_hintergrund_bekommt_seine_id(c, monkeypatch):
    c.AI.update(gid=None, titel="", log=[])

    def weg():
        c.gespraech_oeffnen("b")
    _laufen(c, monkeypatch, [weg, {"gespraech": "neu1", "nachricht": "n"},
                             {"titel": "Neu", "gespraech": "neu1"}, {"token": "x"},
                             {"done": True}])
    assert c.AI["gid"] == "b" and "neu1" in c.AI["ungesehen"]


# ── Abgebrochener Zug im Verlauf (2026-10-09) ─────────────────────────

from tui.ansichten import verlauf as V   # noqa: E402

GRENZE = "Maximale Tool-Tiefe erreicht (8 Runden)"


def _texte(zeilen):
    return ["".join(t for t, _s, _z in z) for z in zeilen]


def _ziele(zeilen):
    return [z for zeile in zeilen for _t, _s, z in zeile if z]


def test_abbruch_live_wird_eintrag_mit_retry_daran(c, monkeypatch):
    _laufen(c, monkeypatch, [{"werkzeug": {"phase": "start", "name": "browser_open",
                                           "args": {"url": "x"}}},
                             {"fehler": GRENZE}, {"antwort": "m3", "ablauf": 4, "abbruch": GRENZE},
                             {"done": True}])
    log = c.AI["log"]
    assert log[-1] == ("abbruch", GRENZE) and c.AI["msg"] == ""   # nicht mehr unten
    zeilen = V.verlauf_zeilen(log, 80, letzte_ai=V.retry_bei(log))
    assert "✗ abgebrochen: " + GRENZE + " · retry" in _texte(zeilen)
    # retry nur am Abbruch, nicht an der alten Antwort davor
    assert [z for z in _ziele(zeilen) if z[0] == "wiederholen"] == [("wiederholen", len(log) - 1)]


def test_retry_ersetzt_den_abbruch(c, monkeypatch):
    c.AI["log"] = [("user", "alt"), ("ai", "alte antwort"), ("user", "neu"),
                   ("werkzeug", "browser_open(url=x)"), ("abbruch", GRENZE)]
    gesendet = []
    monkeypatch.setattr(c, "senden", lambda frage, **k: gesendet.append((frage, k)))
    c.wiederholen()
    assert gesendet == [("neu", {"wiederholen": True})]
    assert c.AI["log"] == [("user", "alt"), ("ai", "alte antwort"), ("user", "neu")]


def test_alter_abbruch_aus_dem_verlauf_wird_genauso_gezeigt():
    h = [{"role": "user", "content": "stundenplan"},
         {"role": "assistant", "content": "", "fehler": GRENZE,
          "werkzeuge": [{"name": "browser_open", "args": "url=x"}]},
         {"role": "user", "content": "und jetzt?"},
         {"role": "assistant", "content": "ok"}]
    log = chat_gespraeche.verlauf_aus(h)
    assert log[:3] == [("user", "stundenplan"), ("werkzeug", "browser_open(url=x)"),
                       ("abbruch", GRENZE)]
    # Danach kam noch etwas: retry hängt an der letzten Antwort, nicht am Abbruch.
    assert V.retry_bei(log) == len(log) - 1
    assert V.retry_bei(log + [("user", "noch was")]) is None


def test_gestoppt_ohne_text_heisst_einfach_gestoppt():
    z = V.verlauf_zeilen([("user", "x"), ("abbruch", "von Sasha gestoppt")], 60, letzte_ai=1)
    assert "✗ gestoppt · retry" in _texte(z)
