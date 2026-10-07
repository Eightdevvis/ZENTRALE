"""Gedächtnis-Ansicht der TUI ohne Bildschirm (tui/ansichten/gedaechtnis.py,
Phase 3 des Claude-Web-Plans, 2026-10-07): reine Helfer, Tasten gegen ein
gefälschtes Backend, Editor-Weg mit gefälschtem Editor, Zeichnen in eine
Attrappe, und dass /gedaechtnis und /skills im Chat ankommen."""
import curses
import io
import json
import os
import threading
import types
import urllib.error

import pytest

from tui.ansichten import chat as chatmod
from tui.ansichten import chat_befehle, gedaechtnis
from tui.ansichten.gedaechtnis import (Gedaechtnis, editor_befehl, inhalt_zeilen,
                                       naechster_status, reiter)

DATEN = {
    "kernakten": [
        {"akte": "hausregeln", "text": "# Hausregeln\n\n- Nicht duzen.\n", "stand": "s1"},
        {"akte": "steckbrief", "text": "# Sasha\n\n" + "Studiert. " * 40, "stand": "s2"},
        {"akte": "ziele", "text": "", "stand": "s3"}],
    "bereiche": [{"bereich": "dossiers", "titel": ["umzug", "geige"]},
                 {"bereich": "quellen", "titel": []}],
    "skills": [
        {"name": "kurz", "beschreibung": "schnelle auskunft", "status": "aktiv",
         "herkunft": "sasha"},
        {"name": "recherche", "beschreibung": "im netz", "status": "aus", "herkunft": "ki"},
        {"name": "plan", "beschreibung": "woche", "status": "vorgeschlagen", "herkunft": "ki"}]}


# ── Reine Helfer ───────────────────────────────────────────────────────

def test_naechster_status():
    assert naechster_status("aktiv") == "aus"
    assert naechster_status("aus") == "aktiv"
    assert naechster_status("vorgeschlagen") == "aktiv"


def test_editor_befehl_reihenfolge():
    alle = lambda n: "/usr/bin/" + n                       # noqa: E731
    keiner = lambda n: None                                # noqa: E731
    assert editor_befehl({"VISUAL": "code -w", "EDITOR": "vim"}, alle) == ["code", "-w"]
    assert editor_befehl({"EDITOR": "vim"}, alle) == ["vim"]
    assert editor_befehl({}, alle) == ["nano"]
    assert editor_befehl({}, lambda n: "/bin/vi" if n == "vi" else None) == ["vi"]
    assert editor_befehl({"EDITOR": "gibtsnicht"}, lambda n: n == "nano" and "/x") == ["nano"]
    assert editor_befehl({"EDITOR": "'kaputt"}, alle) == ["nano"]
    assert editor_befehl({}, keiner) is None


def test_reiter_passt_oder_kuerzt():
    breit = reiter(1, 80)
    assert "".join(t for t, _ in breit) == "hausregeln · steckbrief · ziele · bereiche · skills"
    assert [t for t, g in breit if g] == ["steckbrief"]
    eng = reiter(4, 30)
    assert eng == [("‹ skills ›  5/5", True)]


def test_inhalt_kernakte_leer_und_voll():
    z, _ = inhalt_zeilen(DATEN, "hausregeln", 40)
    assert ("Hausregeln", "kopf") in z and any("Nicht duzen" in t for t, _ in z)
    z, _ = inhalt_zeilen(DATEN, "ziele", 40)
    assert "noch leer" in z[0][0]
    z, _ = inhalt_zeilen(DATEN, "steckbrief", 30)
    assert len(z) > 5 and all(len(t) <= 30 for t, _ in z)


def test_inhalt_bereiche_nur_titel():
    z, _ = inhalt_zeilen(DATEN, "bereiche", 40)
    texte = [t for t, _ in z]
    assert "dossiers/  (2)" in texte and "  umzug, geige" in texte
    assert "quellen/  (0)" in texte


def test_inhalt_skills_name_status_herkunft():
    z, ziel = inhalt_zeilen(DATEN, "skills", 50, wahl=1)
    assert z[0][0].startswith("  ● kurz") and z[0][0].endswith("an · von dir")
    assert z[ziel][0].startswith("› ○ recherche") and z[ziel][1] == "gewaehlt"
    assert z[ziel][0].endswith("aus · von der ki")
    assert any(t.startswith("  ◌ plan") and "vorgeschlagen" in t for t, _ in z)
    assert all(len(t) <= 50 for t, _ in z)
    assert inhalt_zeilen({"skills": []}, "skills", 40)[0][0][0] == "noch keine skills"


def test_inhalt_ohne_daten_stuerzt_nicht():
    for ab, _ in gedaechtnis.ABSCHNITTE:
        inhalt_zeilen(None, ab, 3)
        inhalt_zeilen({}, ab, 200)


# ── Die Überlagerung mit gefälschtem Backend ──────────────────────────

class FakeChat:
    def __init__(self):
        self.AI = {"msg": "", "liste": None}
        self.z = types.SimpleNamespace(stdscr=types.SimpleNamespace(
            clear=lambda: None, refresh=lambda: None))


@pytest.fixture
def backend(monkeypatch):
    zustand = {"daten": json.loads(json.dumps(DATEN)), "aufrufe": [], "fehler": None}

    def api(pfad, methode="GET", body=None, timeout=3.0):
        zustand["aufrufe"].append((methode, pfad, body))
        if zustand["fehler"]:
            raise zustand["fehler"]
        if pfad == "/api/gedaechtnis":
            return json.loads(json.dumps(zustand["daten"]))
        if pfad.startswith("/api/skills/"):
            name = pfad.split("/")[3]
            s = next(s for s in zustand["daten"]["skills"] if s["name"] == name)
            s["status"] = body["status"]
            return {"skill": dict(s)}
        return {"ok": True}
    monkeypatch.setattr(gedaechtnis, "api_call", api)
    return zustand


def _tippe(g, *tasten):
    for t in tasten:
        g.taste(ord(t) if isinstance(t, str) else t)


def test_oeffnen_und_abschnitte_wechseln(backend):
    c = FakeChat()
    c.AI["liste"] = {"offen": True}
    g = Gedaechtnis(c)
    g.oeffnen()
    assert c.AI["gedaechtnis"]["abschnitt"] == 0 and c.AI["liste"] is None
    _tippe(g, curses.KEY_RIGHT)
    assert g.abschnitt() == "steckbrief"
    _tippe(g, curses.KEY_LEFT, curses.KEY_LEFT)
    assert g.abschnitt() == "skills"                      # rundum
    _tippe(g, "3")
    assert g.abschnitt() == "ziele"
    _tippe(g, 9)
    assert g.abschnitt() == "bereiche"
    _tippe(g, 27)
    assert c.AI["gedaechtnis"] is None


def test_skills_oeffnet_gleich_bei_den_skills(backend):
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen("skills")
    assert g.abschnitt() == "skills"


def test_ohne_verbindung_bleibt_es_zu(backend):
    backend["fehler"] = urllib.error.URLError("weg")
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen()
    assert c.AI["gedaechtnis"] is None and "keine verbindung" in c.AI["msg"]


def test_skill_umschalten(backend):
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen("skills")
    _tippe(g, curses.KEY_DOWN, 10)
    assert ("POST", "/api/skills/recherche/status", {"status": "aktiv"}) in backend["aufrufe"]
    assert c.AI["gedaechtnis"]["daten"]["skills"][1]["status"] == "aktiv"
    assert "recherche" in c.AI["msg"] and "an" in c.AI["msg"]
    _tippe(g, " ")
    assert c.AI["gedaechtnis"]["daten"]["skills"][1]["status"] == "aus"
    _tippe(g, curses.KEY_UP, curses.KEY_UP)                # rundum zum letzten
    assert c.AI["gedaechtnis"]["wahl"] == 2


def test_skill_umschalten_fehler_mit_klartext(backend):
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen("skills")
    backend["fehler"] = urllib.error.HTTPError(
        "u", 404, "x", {}, io.BytesIO(json.dumps({"error": "Den Skill gibt es nicht."}).encode()))
    _tippe(g, 10)
    assert c.AI["msg"] == "den skill gibt es nicht."


def test_enter_in_bereichen_tut_nichts(backend):
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen("bereiche")
    n = len(backend["aufrufe"])
    _tippe(g, 10, "e", " ")
    assert len(backend["aufrufe"]) == n


# ── Editor ─────────────────────────────────────────────────────────────

@pytest.fixture
def editor(monkeypatch, tmp_path):
    """Kein echtes curses, kein echter Editor: der „Editor" ist eine
    Funktion, die die Datei ändert."""
    for f in ("def_prog_mode", "endwin", "reset_prog_mode"):
        monkeypatch.setattr(curses, f, lambda: None)
    monkeypatch.setattr(gedaechtnis, "editor_befehl", lambda: ["fake-editor"])
    monkeypatch.setattr(gedaechtnis.tempfile, "tempdir", str(tmp_path))
    aenderung = {"neu": None}

    def call(cmd):
        pfad = cmd[-1]
        if aenderung["neu"] is not None:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(aenderung["neu"])
        return 0
    monkeypatch.setattr(gedaechtnis.subprocess, "call", call)
    return aenderung


def test_editor_schreibt_mit_stand_zurueck(backend, editor, tmp_path):
    editor["neu"] = "# Hausregeln\n\n- Nicht duzen.\n- Kürzer.\n"
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen()
    _tippe(g, "e")
    puts = [a for a in backend["aufrufe"] if a[0] == "PUT"]
    assert puts == [("PUT", "/api/gedaechtnis/hausregeln",
                     {"text": editor["neu"], "stand": "s1"})]
    assert "gespeichert" in c.AI["msg"]
    assert os.listdir(tmp_path) == []                      # Zwischendatei weg


def test_editor_ohne_aenderung_schickt_nichts(backend, editor, tmp_path):
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen("ziele")
    _tippe(g, 10)
    assert not [a for a in backend["aufrufe"] if a[0] == "PUT"]
    assert c.AI["msg"] == "nichts geändert" and os.listdir(tmp_path) == []


def test_editor_konflikt_laesst_den_text_liegen(backend, editor, tmp_path, monkeypatch):
    editor["neu"] = "- meine fassung\n"
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen()
    echt = gedaechtnis.api_call

    def api(pfad, methode="GET", body=None, timeout=3.0):
        if methode == "PUT":
            raise urllib.error.HTTPError("u", 409, "x", {}, io.BytesIO(
                json.dumps({"error": "Die Akte wurde inzwischen geändert"}).encode()))
        return echt(pfad, methode, body, timeout)
    monkeypatch.setattr(gedaechtnis, "api_call", api)
    _tippe(g, "e")
    liegt = os.listdir(tmp_path)
    assert len(liegt) == 1 and "inzwischen geändert" in c.AI["msg"]
    assert str(tmp_path) in c.AI["msg"]
    with open(os.path.join(tmp_path, liegt[0]), encoding="utf-8") as f:
        assert f.read() == "- meine fassung\n"


def test_ohne_editor_ein_hinweis(backend, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "editor_befehl", lambda: None)
    c = FakeChat()
    g = Gedaechtnis(c)
    g.oeffnen()
    _tippe(g, "e")
    assert "kein editor" in c.AI["msg"]


# ── Zeichnen in eine Attrappe ─────────────────────────────────────────

@pytest.mark.parametrize("breite,hoehe", [(80, 18), (60, 9), (40, 10), (136, 26), (12, 6)])
def test_zeichnen_bleibt_im_kasten(backend, breite, hoehe):
    c = FakeChat()
    gezeichnet = []

    def addclip(y, x, text, w, attr=0):
        gezeichnet.append((y, x, text[:max(0, w)]))
    c.z.C = {k: 0 for k in ("bright", "dim", "faint", "acc", "warn")}
    c.z.addclip = addclip
    g = Gedaechtnis(c)
    for ab, _ in gedaechtnis.ABSCHNITTE:
        g.oeffnen(ab)
        c.AI["msg"] = "eine meldung"
        gezeichnet.clear()
        g.zeichnen(0, 0, hoehe, breite)
        for y, x, text in gezeichnet:
            assert 0 <= y < hoehe and x + len(text) <= breite, (ab, y, x, text)


# ── Im Chat ────────────────────────────────────────────────────────────

def test_befehle_sind_bekannt():
    for roh, name in (("/gedaechtnis", "gedaechtnis"), ("/gedächtnis", "gedaechtnis"),
                      ("/memory", "gedaechtnis"), ("/skills", "skills")):
        e = chat_befehle.lesen(roh)
        assert (e.art, e.name) == ("befehl", name), roh
    hilfe = chat_befehle.hilfe_text()
    assert "/gedaechtnis" in hilfe and "/skills" in hilfe


def test_chat_leitet_befehl_und_tasten_weiter(backend):
    c = chatmod.Chat.__new__(chatmod.Chat)
    c.AI = {"msg": "", "liste": None, "perm": None, "wahl": None, "streaming": False}
    c.AI_LOCK = threading.Lock()
    c.z = types.SimpleNamespace(C={k: 0 for k in ("bright", "dim", "faint", "acc", "warn")},
                                addclip=lambda *a, **k: None)
    c.liste = types.SimpleNamespace(oeffnen=lambda: None)
    c.gedaechtnis = Gedaechtnis(c)
    c.befehl("skills", "")
    assert c.gedaechtnis.abschnitt() == "skills"
    assert "enter an/aus" in c.fusszeile()
    c.taste(curses.KEY_RIGHT)
    assert c.gedaechtnis.abschnitt() == "hausregeln"
    c.befehl("gedaechtnis", "")
    assert c.AI["gedaechtnis"] is not None
    c.taste(-1)
    assert c.AI["gedaechtnis"] is not None
