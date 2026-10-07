"""TUI-Seite der Nachbesserungen (2026-10-07): die Erlaubnis-Frage mit
Geltung, /erlaubnis, und /modell mit vielen Modellen (tippen filtert)."""
import curses
from types import SimpleNamespace

import pytest

from tui.ansichten import chat, chat_befehle, chat_erlaubnis


class _Schirm:
    def __init__(self):
        self.folge = []

    def getch(self):
        return self.folge.pop(0) if self.folge else -1

    def timeout(self, ms):
        pass

    def nodelay(self, an):
        pass


@pytest.fixture
def ch():
    c = chat.Chat(SimpleNamespace(stdscr=_Schirm(), C={}))
    c.antworten = []
    c.ai_answer_perm = lambda o: c.antworten.append(o)
    c.AI["active"] = True
    return c


KNOEPFE = ["ja, nur dieses mal", "ja, für dieses gespräch", "ja, immer", "nein"]


@pytest.mark.parametrize("taste,antwort", [
    (ord("j"), "ja, nur dieses mal"), (ord("n"), "nein"),
    (ord("2"), "ja, für dieses gespräch"), (ord("3"), "ja, immer"),
])
def test_erlaubnis_frage_tasten(ch, taste, antwort):
    ch.AI["perm"] = {"frage": "Soll ich?", "optionen": KNOEPFE, "erlaubnis": True}
    ch.taste(taste)
    assert ch.antworten == [antwort]


def test_esc_lehnt_ab(ch):
    ch.AI["perm"] = {"frage": "Soll ich?", "optionen": KNOEPFE}
    ch.taste(27)
    assert ch.antworten == ["nein"]


# ── /modell: viele Modelle, tippen filtert ──────────────────────────────

STAND = {
    "anbieter_aktiv": "qwen", "modell": "qwen-plus",
    "anbieter_liste": [
        {"name": "qwen", "schluessel": True, "spricht": True,
         "modelle": ["qwen-plus", "qwen-turbo"] + ["qwen%d-modell" % i for i in range(300)]},
        {"name": "claude", "schluessel": True, "spricht": True,
         "modelle": ["claude-sonnet-5"]},
    ],
}


def test_alle_modelle_in_der_auswahl():
    w = chat.auswahl("modell", STAND)
    assert len(w["optionen"]) == 303 and w["idx"] == 0


def test_tippen_filtert_ziffern_gehoeren_zum_filter(ch):
    gesetzt = []
    ch.setzen = gesetzt.append
    ch.AI["wahl"] = chat.auswahl("modell", STAND)
    for z in "qwen12":
        ch.taste(ord(z))
    texte = [o[0] for o in ch.AI["wahl"]["optionen"]]
    assert texte and all("qwen12" in t for t in texte)
    assert gesetzt == []
    ch.taste(127)                          # ⌫
    assert ch.AI["wahl"]["filter"] == "qwen1"
    for z in " sonnet":                    # mehrere Wörter: alle müssen passen
        ch.taste(ord(z))
    assert ch.AI["wahl"]["optionen"] == []
    ch.taste(10)                           # nichts passt: Enter tut nichts
    assert gesetzt == [] and ch.AI["wahl"] is not None
    for _ in range(len(" sonnet") + len("qwen1")):
        ch.taste(127)
    for z in "sonnet":
        ch.taste(ord(z))
    ch.taste(10)
    assert gesetzt == [{"anbieter": "claude", "modell": "claude-sonnet-5"}]


def test_filter_behaelt_die_gewaehlte():
    w = chat.auswahl("modell", STAND)
    w["idx"] = 1                           # qwen-turbo
    chat.wahl_filtern(w, "turbo")
    assert w["optionen"][w["idx"]][0] == "qwen · qwen-turbo"


def test_fuss_zeigt_zahl_und_filter(ch):
    from collections import defaultdict
    ch.z.C = defaultdict(int)
    w = chat.wahl_filtern(chat.auswahl("modell", STAND), "qwen-")
    zeilen = ch._fuss_wahl(w, 80, 24)
    assert "2 von 303" in zeilen[0][0] and "filter: qwen-" in zeilen[0][0]
    leer = chat.wahl_filtern(chat.auswahl("modell", STAND), "gibtsnicht")
    assert any("nichts passt" in z[0] for z in ch._fuss_wahl(leer, 80, 24))


# ── /erlaubnis ─────────────────────────────────────────────────────────

def test_befehl_bekannt():
    assert chat_befehle.lesen("/erlaubnis") == ("befehl", "erlaubnis", "", "/erlaubnis")


def test_uebersicht_text_und_auswahl():
    stand = {"immer": [{"name": "run_code", "was": "programme abgeschottet ausführen"}],
             "gespraech": [{"name": "web_search", "was": "im internet suchen"}]}
    text = chat_erlaubnis.zeilen(stand)
    assert "immer: programme abgeschottet ausführen" in text
    assert "in diesem gespräch: im internet suchen" in text
    w = chat_erlaubnis.auswahl(stand, aktion=None)
    assert [o[1] for o in w["optionen"]] == [{"werkzeug": "run_code"},
                                             {"werkzeug": "web_search"}, {"alle": True}]
    leer = {"immer": [], "gespraech": []}
    assert chat_erlaubnis.auswahl(leer, None) is None
    assert "nichts ist dauerhaft erlaubt" in chat_erlaubnis.zeilen(leer)


def test_erlaubnis_befehl_zeigt_und_nimmt_zurueck(ch, monkeypatch):
    rufe = []

    def api(pfad, methode="GET", daten=None):
        rufe.append((pfad, methode, daten))
        if pfad == "/api/erlaubnis":
            return {"immer": [{"name": "run_code", "was": "programme"}], "gespraech": []}
        return {"weg": ["run_code"]}
    monkeypatch.setattr(chat_erlaubnis, "api_call", api)
    ch.befehl("erlaubnis", "")
    assert ch.AI["log"][-1][0] == "hinweis"
    assert ch.AI["wahl"]["titel"] == "erlaubnis zurücknehmen?"
    ch.taste(10)
    assert rufe[-1] == ("/api/erlaubnis/zuruecknehmen", "POST", {"werkzeug": "run_code"})
    assert "zurückgenommen" in ch.AI["msg"]
