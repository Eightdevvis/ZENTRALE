"""Ablage und Anhänge in der TUI ohne Bildschirm (tui/ansichten/ablage.py,
chat_ablage.py) — Claude-Web-Plan Phase 5, 2026-10-07."""
import curses
import threading
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest

from tui.ansichten import ablage as ablagemod
from tui.ansichten import chat as chatmod
from tui.ansichten import chat_ablage, chat_befehle, chat_gespraeche
from tui.ansichten.ablage import Ablageliste, lese_zeilen, listen_zeilen

JETZT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _vor(**k):
    return (JETZT - timedelta(**k)).isoformat()


# ── Reine Helfer ─────────────────────────────────────────────────────────

def test_listen_zeilen_titel_art_alter_und_breite():
    e = [{"id": "a", "titel": "Packliste", "art": "markdown", "herkunft": "ki",
          "geaendert": _vor(minutes=5)},
         {"id": "b", "titel": "Ein sehr langer Titel, der nirgends hinpasst", "art": "bild",
          "herkunft": "anhang", "geaendert": _vor(days=2), "fassung": 3,
          "gespraech_titel": "Urlaub"}]
    z = listen_zeilen(e, 1, 40, JETZT)
    assert z[0][0].startswith("  Packliste") and z[0][0].endswith("text · vor 5 Min.")
    assert z[1][0].startswith("› ") and "…" in z[1][0] and z[1][0].endswith("anhang · vor 2 Tagen")
    assert all(len(t) <= 40 for t, _ in z) and z[1][1] == "gewaehlt"
    breit = listen_zeilen(e, 0, 90, JETZT)[1][0]
    assert "(v3)" in breit and "— Urlaub" in breit


def test_lese_zeilen_markdown_code_bild():
    md = lese_zeilen({"kopf": {"art": "markdown"}, "inhalt": "# Titel\n- eins"}, 30)
    assert ("Titel", "kopf") in md or any(s == "kopf" for _t, s in md)
    code = lese_zeilen({"kopf": {"art": "code"}, "inhalt": "def f():\n\treturn " + "x" * 40}, 20)
    assert code[0] == ("def f():", "code") and all(len(t) <= 20 for t, _ in code)
    assert code[1][0].startswith("    return")          # Einrückung bleibt
    bild = lese_zeilen({"kopf": {"art": "bild"}, "inhalt": None, "bytes": 4096,
                        "pfad": "/x/v1-pc.png"}, 30)
    assert any("bild" in t for t, _ in bild) and any("/x/v1-pc.png" in t for t, _ in bild)


def test_chat_zeilen_fuer_ablage_und_anhang():
    rolle, text = chat_ablage.ablage_eintrag({"id": "d1", "titel": "Plan"})
    assert rolle == "ablage" and chat_ablage.ablage_anzeige(text, True) == "Plan — enter öffnet"
    assert chat_ablage.ablage_anzeige(text, False) == "Plan — in /ablage"
    log = [("user", "x"), ("ablage", "d1\tPlan"), ("ai", "y"), ("ablage", "d2\tListe")]
    assert chat_ablage.letztes_dokument(log) == "d2"
    assert chat_ablage.letztes_dokument([("user", "x")]) is None
    assert chatmod.ai_wrap("ablage", "Plan — enter öffnet", 40)[0][1].startswith("  ▤ Plan")


def test_pfad_aufloesen(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert chat_ablage.pfad_aufloesen(" '%s' " % (tmp_path / "a.txt")) == str(tmp_path / "a.txt")
    assert chat_ablage.pfad_aufloesen("~").startswith("/")
    assert chat_ablage.pfad_aufloesen("") == ""


def test_verlauf_aus_zeigt_anhaenge_und_dokumente():
    h = [{"role": "user", "content": "kuerz das", "anhaenge": [{"id": "a1", "titel": "brief.txt"}]},
         {"role": "assistant", "content": "Erledigt.",
          "werkzeuge": [{"name": "create_document", "args": "titel=Kurz"}],
          "dokumente": [{"id": "d1", "titel": "Kurz"}]}]
    log = chat_gespraeche.verlauf_aus(h)
    assert log == [("user", "kuerz das"), ("anhang", "anhang: brief.txt"),
                   ("werkzeug", "create_document(titel=Kurz)"), ("ablage", "d1\tKurz"),
                   ("ai", "Erledigt.")]


def test_befehle_sind_bekannt():
    assert chat_befehle.lesen("/ablage").art == "befehl"
    a = chat_befehle.lesen("/anhang ~/Downloads/foto.png")
    assert (a.art, a.name, a.arg) == ("befehl", "anhang", "~/Downloads/foto.png")
    assert "/anhang" in chat_befehle.hilfe_text()


# ── Die Überlagerung mit gefälschtem Backend ──────────────────────────

class FakeZ:
    def __init__(self):
        self.C = defaultdict(int)
        self.zeilen = []

    def addclip(self, y, x, text, w, attr=0):
        assert w >= 0
        self.zeilen.append((y, x, str(text)[:max(0, w)]))

    def safe_addstr(self, y, x, text, attr=0):
        self.zeilen.append((y, x, str(text)))


class FakeChat:
    def __init__(self):
        self.AI = {"msg": "", "ablage": None, "log": [], "anhaenge": [], "gid": "g1"}
        self.AI_LOCK = threading.Lock()
        self.z = FakeZ()


DOKS = [{"id": "d1", "titel": "Packliste", "art": "markdown", "fassung": 2,
         "geaendert": _vor(minutes=3)},
        {"id": "d2", "titel": "Skizze", "art": "bild", "herkunft": "anhang",
         "geaendert": _vor(hours=3)}]


@pytest.fixture
def backend(monkeypatch):
    aufrufe = []

    def api(pfad, methode="GET", body=None, timeout=3.0):
        aufrufe.append((methode, pfad, body))
        if pfad.startswith("/api/ablage?archiv"):
            return {"dokumente": []}
        if pfad == "/api/ablage":
            return {"dokumente": DOKS}
        if pfad.startswith("/api/ablage/d1"):
            f = 1 if "fassung=1" in pfad else 2
            return {"kopf": {"id": "d1", "titel": "Packliste", "art": "markdown", "fassung": 2},
                    "fassung": f, "inhalt": "\n".join("- punkt %d (v%d)" % (i, f) for i in range(60))}
        if pfad.startswith("/api/ablage/weg"):
            raise urllib.error.HTTPError(pfad, 404, "x", {}, None)
        return {}
    monkeypatch.setattr(ablagemod, "api_call", api)
    return aufrufe


def test_liste_waehlen_lesen_blaettern_fassung_zurueck(backend):
    c = FakeChat()
    a = Ablageliste(c)
    a.oeffnen()
    assert c.AI["ablage"]["eintraege"] == DOKS
    a.taste(curses.KEY_DOWN)
    a.taste(curses.KEY_UP)
    a.taste(10)
    L = c.AI["ablage"]["lesen"]
    assert L["fassung"] == 2 and "(v2)" in L["dok"]["inhalt"]
    a.zeichnen(0, 0, 24, 80)                      # setzt die Seitenhöhe
    a.taste(curses.KEY_NPAGE)
    assert c.AI["ablage"]["lesen"]["scroll"] > 0
    a.taste(curses.KEY_END)
    a.zeichnen(0, 0, 24, 80)
    assert c.AI["ablage"]["lesen"]["scroll"] == 60 - (24 - 2 - 1 - 3 + 1)
    a.taste(curses.KEY_LEFT)
    assert c.AI["ablage"]["lesen"]["fassung"] == 1
    a.taste(curses.KEY_LEFT)
    assert "erste fassung" in c.AI["msg"]
    a.taste(27)                                   # zurück zur Liste
    assert c.AI["ablage"]["lesen"] is None and c.AI["ablage"]["eintraege"]
    a.taste(27)                                   # zu
    assert c.AI["ablage"] is None


def test_archivieren_ruft_das_backend(backend):
    c = FakeChat()
    a = Ablageliste(c)
    a.oeffnen()
    a.taste(ord("a"))
    assert ("POST", "/api/ablage/d1/archiv", {"an": True}) in backend
    assert "archiviert" in c.AI["msg"]
    a.taste(ord("z"))
    assert c.AI["ablage"]["archiv"] and c.AI["ablage"]["eintraege"] == []


def test_direkt_gelesen_fuehrt_esc_zurueck_in_den_chat(backend):
    c = FakeChat()
    a = Ablageliste(c)
    a.lesen("d1", direkt=True)
    a.taste(27)
    assert c.AI["ablage"] is None


def test_unbekanntes_dokument_klare_meldung(backend):
    c = FakeChat()
    Ablageliste(c).lesen("weg")
    assert c.AI["ablage"] is None and "nicht" in c.AI["msg"]


@pytest.mark.parametrize("groesse", [(24, 80), (30, 136), (6, 20), (3, 8)])
def test_zeichnen_stuerzt_nicht_ab(backend, groesse):
    c = FakeChat()
    a = Ablageliste(c)
    a.oeffnen()
    hoehe, breite = groesse
    a.zeichnen(0, 0, hoehe, breite)
    a.lesen("d1")
    a.zeichnen(0, 0, hoehe, breite)
    c.AI["ablage"]["lesen"]["dok"] = {"kopf": {"art": "bild", "titel": "x"}, "inhalt": None,
                                     "bytes": 10, "pfad": "/p"}
    a.zeichnen(0, 0, hoehe, breite)
    assert c.z.zeilen


# ── Der Chat: Enter öffnet, Anhänge ───────────────────────────────────

def _chat(monkeypatch):
    c = chatmod.Chat(FakeZ())
    monkeypatch.setattr(c, "_esc_lesen", lambda: "esc")    # Esc allein, ohne Bildschirm
    return c


def test_enter_bei_leerer_eingabe_liest_das_neueste_dokument(backend, monkeypatch):
    c = _chat(monkeypatch)
    c.AI["log"] = [("user", "mach"), ("ablage", "d1\tPackliste")]
    c.taste(10)
    assert c.AI["ablage"]["lesen"]["dok"]["kopf"]["id"] == "d1"
    c.taste(27)
    assert c.AI["ablage"] is None
    # Ohne Dokument tut Enter bei leerer Eingabe nichts.
    c.AI["log"] = [("user", "x")]
    c.taste(10)
    assert c.AI["ablage"] is None


def test_befehl_ablage_oeffnet_die_liste(backend, monkeypatch):
    c = _chat(monkeypatch)
    c.befehl("ablage", "")
    assert c.AI["ablage"]["eintraege"] == DOKS
    assert "ablage" in c.fusszeile()


def test_anhang_lesen_schicken_vormerken(tmp_path, monkeypatch):
    c = _chat(monkeypatch)
    datei = tmp_path / "rezept.md"
    datei.write_text("# Pfannkuchen")
    gesendet = []

    def api(pfad, methode="GET", body=None, timeout=3.0):
        gesendet.append((pfad, body))
        return {"id": "a1", "titel": "rezept.md", "art": "markdown", "hinweis": ""}
    monkeypatch.setattr(chat_ablage, "api_call", api)
    monkeypatch.setattr(chat_ablage.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    c.anhang_dazu(str(datei))
    assert gesendet[0][0] == "/api/anhang" and gesendet[0][1]["pfad"] == str(datei)
    assert c.AI["anhaenge"] == [{"id": "a1", "titel": "rezept.md", "art": "markdown"}]
    assert "angehängt" in c.AI["msg"] and "rezept.md" in c.anhaenge_text()
    # Senden nimmt sie mit und zeigt sie im Verlauf.
    gestartet = []
    monkeypatch.setattr(chatmod.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda s: gestartet.append(args)})())
    c.senden("was koche ich?")
    assert gestartet[0][3] == [{"id": "a1", "titel": "rezept.md", "art": "markdown"}]
    assert c.AI["anhaenge"] == [] and ("anhang", "anhang: rezept.md") in c.AI["log"]


def test_anhang_fehler_sind_klartext(tmp_path, monkeypatch):
    c = _chat(monkeypatch)
    c.anhang_dazu(str(tmp_path / "gibtsnicht.txt"))
    assert "gibt es nicht" in c.AI["msg"]
    c.anhang_dazu("")
    assert "/anhang <pfad>" in c.AI["msg"]
    datei = tmp_path / "x.txt"
    datei.write_text("x")
    import io

    def api(*a, **k):
        raise urllib.error.HTTPError("u", 400, "x", {}, io.BytesIO(
            b'{"error": "der Ordner enth\\u00e4lt Schl\\u00fcssel"}'))
    monkeypatch.setattr(chat_ablage, "api_call", api)
    c._anhang_senden(str(datei))
    assert c.AI["msg"].startswith("nicht angehängt: der Ordner") and c.AI["anhaenge"] == []
