"""
Das Eingabefeld und die Slash-Befehle des TUI-Chats (Claude-Web-Plan,
Phase 1, 2026-10-07): Cursor, Umlaute, Alt+Enter, Löschen an der
Cursorstelle, Umbruch — und dass ein Befehl nie als Frage an die KI geht.
"""
import curses
from types import SimpleNamespace

import pytest

from tui.ansichten import chat, chat_befehle, eingabe


# ── Editor als reine Funktionen ───────────────────────────────────────

def _tippe(text, pos, s):
    for z in s:
        text, pos = eingabe.einfuegen(text, pos, z)
    return text, pos


def test_einfuegen_an_der_cursorstelle():
    t, p = _tippe("", 0, "Hallo")
    t, p = eingabe.links(t, p)
    t, p = eingabe.links(t, p)
    t, p = eingabe.einfuegen(t, p, "X")
    assert (t, p) == ("HalXlo", 4)


def test_backspace_und_entf_an_der_position():
    t, p = "abcd", 2
    assert eingabe.zurueck(t, p) == ("acd", 1)
    assert eingabe.entfernen(t, p) == ("abd", 2)
    assert eingabe.zurueck("abc", 0) == ("abc", 0)
    assert eingabe.entfernen("abc", 3) == ("abc", 3)


def test_cursor_bleibt_im_text():
    assert eingabe.links("ab", 0) == ("ab", 0)
    assert eingabe.rechts("ab", 2) == ("ab", 2)


def test_pos1_und_ende_gelten_fuer_die_aktuelle_zeile():
    t = "erste\nzweite zeile\ndritte"
    p = t.index("te zeile")
    assert eingabe.zeilenanfang(t, p)[1] == t.index("zweite")
    assert eingabe.zeilenende(t, p)[1] == t.index("\ndritte")
    assert eingabe.zeilenende(t, len(t))[1] == len(t)


def test_hoch_runter_halten_die_spalte():
    t = "abcdef\nxy\n12345"
    p = 4                                         # hinter "abcd"
    t, p = eingabe.runter(t, p)
    assert p == t.index("xy") + 2                 # Zeile ist kürzer → ans Ende
    t, p = eingabe.runter(t, p)
    assert p == t.index("12345") + 2
    assert eingabe.runter(t, p)[1] == len(t)      # letzte Zeile → ans Ende
    assert eingabe.hoch(t, 3)[1] == 0             # erste Zeile → an den Anfang


def test_grenze():
    t, p = eingabe.einfuegen("abc", 3, "defg", grenze=5)
    assert t == "abcde"


def test_umlaute_aus_einzelnen_bytes():
    puffer, raus = b"", []
    for b in "Grüße ✓".encode("utf-8"):
        if b < 128:
            raus.append(chr(b))
            continue
        puffer, z = eingabe.utf8_byte(puffer, b)
        if z:
            raus.append(z)
    assert "".join(raus) == "Grüße ✓" and puffer == b""


def test_kaputtes_utf8_haengt_nicht_ewig():
    puffer = b""
    for b in (0xF0, 0x80, 0x80, 0x41 | 0x80):
        puffer, z = eingabe.utf8_byte(puffer, b)
    assert puffer == b"" and z is None


def test_esc_folge_unterscheidet_esc_und_alt_enter():
    assert eingabe.esc_folge([]) == "esc"
    assert eingabe.esc_folge([13]) == "alt_enter"
    assert eingabe.esc_folge([10]) == "alt_enter"
    assert eingabe.esc_folge([curses.KEY_ENTER]) == "alt_enter"
    assert eingabe.esc_folge([91, 49, 59, 51, 68]) is None   # Alt+← roh
    assert eingabe.esc_folge([ord("x")]) is None


def test_anzeige_bricht_um_und_findet_den_cursor():
    zeilen, y, x, oben = eingabe.anzeige("abcdefgh", 8, 4, 5)
    assert zeilen == ["abcd", "efgh", ""] and (y, x, oben) == (2, 0, 0)
    zeilen, y, x, _ = eingabe.anzeige("ab\ncd", 3, 10, 5)
    assert zeilen == ["ab", "cd"] and (y, x) == (1, 0)
    zeilen, y, x, _ = eingabe.anzeige("", 0, 10, 5)
    assert zeilen == [""] and (y, x) == (0, 0)
    zeilen, y, x, _ = eingabe.anzeige("abcdef", 2, 4, 5)   # mitten im ersten Stück
    assert zeilen == ["abcd", "ef"] and (y, x) == (0, 2)


def test_anzeige_waechst_bis_zur_hoehe_dann_scrollt_sie():
    text = "\n".join(str(i) for i in range(9))
    zeilen, y, x, oben = eingabe.anzeige(text, len(text), 10, 5)
    assert zeilen == ["4", "5", "6", "7", "8"] and y == 4 and oben == 4
    zeilen, y, x, oben = eingabe.anzeige(text, 0, 10, 5)
    assert zeilen[0] == "0" and y == 0 and oben == 0


# ── Slash-Befehle lesen ───────────────────────────────────────────────

@pytest.mark.parametrize("roh, art, name, arg, text", [
    ("wie spät?", "senden", "", "", "wie spät?"),
    ("  /neu  ", "befehl", "neu", "", "/neu"),
    ("/modell claude-opus-5", "befehl", "modell", "claude-opus-5", None),
    ("/Effort HIGH", "befehl", "effort", "HIGH", None),
    ("/budget 12,50", "befehl", "budget", "12,50", None),
    ("/help", "befehl", "hilfe", "", None),
    ("/clear", "befehl", "neu", "", None),
    ("//etc/hosts lesen", "senden", "", "", "/etc/hosts lesen"),
    ("/modl x", "unbekannt", "modl", "x", None),
    ("/", "unbekannt", "", "", None),
    ("   ", "leer", "", "", ""),
])
def test_slash_lesen(roh, art, name, arg, text):
    e = chat_befehle.lesen(roh)
    assert (e.art, e.name, e.arg) == (art, name, arg)
    if text is not None:
        assert e.text == text


def test_hilfe_nennt_alle_befehle():
    h = chat_befehle.hilfe_text()
    for b, _ in chat_befehle.BEFEHLE:
        assert b in h


# ── Auswahl und Statuszeile (reine Helfer in chat.py) ──────────────────

STAND = {
    "anbieter": "auto", "anbieter_aktiv": "claude", "modell": "claude-haiku-4-5",
    "effort": "low", "effort_stufen": ["low", "medium", "high"],
    "effort_wirkt": True, "budget": None,
    "budget_lage": {"ausgegeben": 1.234}, "weg": "auto",
    "anbieter_liste": [
        {"name": "claude", "schluessel": True, "spricht": True,
         "modelle": ["claude-sonnet-5", "claude-haiku-4-5"]},
        {"name": "grok", "schluessel": False, "spricht": True, "modelle": ["grok-4"]},
        {"name": "qwen", "schluessel": True, "spricht": True, "modelle": ["qwen-plus"]},
    ],
}


def test_modell_auswahl_nur_mit_schluessel_und_steht_auf_dem_aktuellen():
    w = chat.auswahl("modell", STAND)
    texte = [o[0] for o in w["optionen"]]
    assert texte == ["claude · claude-sonnet-5", "claude · claude-haiku-4-5",
                     "qwen · qwen-plus"]
    assert w["idx"] == 1
    assert w["optionen"][2][1] == {"anbieter": "qwen", "modell": "qwen-plus"}


def test_anbieter_und_effort_auswahl():
    assert [o[0] for o in chat.auswahl("anbieter", STAND)["optionen"]] == \
        ["auto", "claude", "qwen"]
    w = chat.auswahl("effort", STAND)
    assert w["idx"] == 0 and w["optionen"][2][1] == {"effort": "high"}


def test_statuszeilen():
    assert "kein budget" in chat.budget_text(STAND)
    assert "1,23€" in chat.budget_text(STAND)
    assert chat.stand_text({"weg": "lokal"}, dict(STAND, weg="local")) == "nur lokal"
    assert "claude-haiku" in chat.stand_text({"modell": "x"}, STAND)
    assert "jetzt claude" in chat.stand_text({"anbieter": "auto"}, STAND)


# ── Tasten im Chat (ohne Bildschirm) ──────────────────────────────────

class _Schirm:
    """stdscr-Ersatz: getch liefert, was nach einem ESC 'folgt'."""

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
    z = SimpleNamespace(stdscr=_Schirm(), C={})
    c = chat.Chat(z)
    c.gesendet, c.gestoppt, c.befehle = [], [], []
    c.senden = lambda text: c.gesendet.append(text)
    c.stoppen = lambda: c.gestoppt.append(True)
    c.befehl = lambda n, a: c.befehle.append((n, a))
    c.AI["active"] = True
    return c


def _tasten(c, text):
    for b in text.encode("utf-8"):
        c.taste(b)


def test_umlaute_tippen(ch):
    _tasten(ch, "Grüße aus Köln")
    assert ch.AI["input"] == "Grüße aus Köln"
    assert ch.AI["cur"] == len("Grüße aus Köln")


def test_alt_enter_macht_eine_neue_zeile_enter_schickt(ch):
    _tasten(ch, "eins")
    ch.z.stdscr.folge = [13]            # ESC, dann CR = Alt+Enter
    ch.taste(27)
    _tasten(ch, "zwei")
    assert ch.AI["input"] == "eins\nzwei" and ch.AI["active"]
    ch.taste(10)
    assert ch.gesendet == ["eins\nzwei"]


def test_backspace_an_der_cursorstelle(ch):
    _tasten(ch, "abcd")
    ch.taste(curses.KEY_LEFT)
    ch.taste(curses.KEY_BACKSPACE)
    assert (ch.AI["input"], ch.AI["cur"]) == ("abd", 2)
    ch.taste(curses.KEY_HOME)
    ch.taste(curses.KEY_DC)
    assert ch.AI["input"] == "bd"


def test_pfeile_scrollen_einzeilig_und_bewegen_mehrzeilig(ch):
    _tasten(ch, "eine zeile")
    ch.taste(curses.KEY_UP)
    assert ch.AI["scroll"] == 1 and ch.AI["cur"] == len("eine zeile")
    ch.AI["scroll"] = 0
    ch.AI["input"], ch.AI["cur"] = "ab\ncd", 5
    ch.taste(curses.KEY_UP)
    assert ch.AI["scroll"] == 0 and ch.AI["cur"] == 2


def test_esc_stoppt_waehrend_einer_antwort_sonst_zu(ch):
    ch.AI["streaming"] = True
    ch.taste(27)
    assert ch.gestoppt == [True] and ch.AI["active"]
    ch.AI["streaming"] = False
    ch.taste(27)
    assert not ch.AI["active"]


def test_andere_alt_taste_tut_nichts(ch):
    ch.z.stdscr.folge = [ord("x")]
    ch.taste(27)
    assert ch.AI["active"] and ch.AI["input"] == ""


def test_unbekannter_befehl_geht_nicht_an_die_ki(ch):
    _tasten(ch, "/modl")
    ch.taste(10)
    assert ch.gesendet == [] and ch.befehle == []
    assert "unbekannter befehl" in ch.AI["msg"]
    assert ch.AI["input"] == "/modl"      # zum Korrigieren stehen lassen


def test_befehl_und_doppelter_schraegstrich(ch):
    _tasten(ch, "/effort high")
    ch.taste(10)
    assert ch.befehle == [("effort", "high")] and ch.AI["input"] == ""
    _tasten(ch, "//etc")
    ch.taste(10)
    assert ch.gesendet == ["/etc"]


def test_waehrend_der_antwort_tippen_aber_nicht_schicken(ch):
    ch.AI["streaming"] = True
    _tasten(ch, "nächste frage")
    ch.taste(10)
    assert ch.gesendet == [] and ch.AI["input"] == "nächste frage"
    assert "esc stoppt" in ch.AI["msg"]


def test_auswahl_mit_pfeil_und_enter(ch):
    gesetzt = []
    ch.setzen = lambda d: gesetzt.append(d)
    ch.AI["wahl"] = chat.auswahl("effort", STAND)
    ch.taste(curses.KEY_DOWN)
    ch.taste(10)
    assert gesetzt == [{"effort": "medium"}] and ch.AI["wahl"] is None
    ch.AI["wahl"] = chat.auswahl("effort", STAND)
    ch.taste(27)
    assert ch.AI["wahl"] is None and ch.AI["active"]
