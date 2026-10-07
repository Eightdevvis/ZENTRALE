"""Skills (Phase 4 des Claude-Web-Plans, 2026-10-07): Anleitungen für eine Art
Aufgabe, als Dateien im Gedächtnis; im festen Prompt nur die Liste, der
Inhalt per load_skill. Anlegen (propose_skill) und Umschreiben (edit_skill)
nur nach Sashas Ja.

Geprüft wird Verhalten:
  - die Liste im Prompt ist deterministisch und zeigt nur aktive Skills,
  - load_skill liefert den Inhalt, und nur von aktiven,
  - propose_skill ist gegatet: Ja legt an, Nein legt nichts an,
  - edit_skill ändert nur bestehende und lässt eine .bak liegen,
  - die Erstbefüllung überschreibt nie etwas,
  - klein bleibt unverändert. (Wächter gegen das echte data/:
    tests/test_keine_seiteneffekte.py)
"""
import os

import pytest

import cloud
import gedaechtnis
import ki_werkzeuge
import skills
import state
import werkzeug_register
import werkzeug_schleife
from profil import gross, klein


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


def _ordner():
    return gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)


def _skill(name, status="aktiv", beschreibung=None, inhalt="Schritt eins.",
           herkunft="sasha"):
    os.makedirs(_ordner(), exist_ok=True)
    text = (f"## {name}\n- beschreibung: {beschreibung or 'wenn ' + name}\n"
            f"- erstellt: 2026-10-07\n- herkunft: {herkunft}\n"
            f"- status: {status}\n\n{inhalt}\n")
    with open(os.path.join(_ordner(), f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(text)


def _leer():
    """Ein Skill-Ordner OHNE Vorlagen (er existiert, also keine Erstbefüllung)."""
    os.makedirs(_ordner(), exist_ok=True)


def _fahren(gen):
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as e:
        return events, e.value


def _werkzeug(name, args, antwort):
    """Einen Werkzeug-Aufruf durch die echte Schleife samt Gate schicken."""
    state_antwort = {"wert": antwort}
    gefragt = []
    orig_req, orig_wait = state.request_permission, state.wait_permission
    state.request_permission = lambda **k: gefragt.append(True)
    state.wait_permission = lambda: state_antwort["wert"]
    try:
        events, erg = _fahren(werkzeug_schleife.run_tool(
            name, args, tutor_mode=False, active_exec=ki_werkzeuge.ausfuehren,
            user_query=""))
    finally:
        state.request_permission, state.wait_permission = orig_req, orig_wait
    fragen = [e["permission"]["frage"] for e in events if "permission" in e]
    return fragen, erg


# ── Die Liste im Prompt ───────────────────────────────────────────────

def test_liste_nur_aktive_und_nach_name_sortiert():
    _leer()
    _skill("zebra")
    _skill("apfel")
    _skill("mitte", status="aus")
    _skill("neu", status="vorgeschlagen")
    block = skills.prompt_block()
    assert "- apfel — wenn apfel" in block
    assert block.index("apfel") < block.index("zebra")
    assert "mitte" not in block and "neu" not in block
    assert "load_skill" in block


def test_liste_ist_byte_stabil():
    """Der Prompt-Cache bricht, sobald sich der feste Teil ändert."""
    _leer()
    _skill("b")
    _skill("a")
    assert skills.prompt_block() == skills.prompt_block()


def test_datei_ohne_kopf_zaehlt_als_aus():
    _leer()
    with open(os.path.join(_ordner(), "kaputt.md"), "w") as f:
        f.write("einfach Text\n")
    assert skills.prompt_block() == ""
    assert [s["status"] for s in skills.alle()] == ["aus"]


def test_ohne_aktive_skills_kein_block():
    _leer()
    assert skills.prompt_block() == ""


def test_liste_steht_im_festen_teil_der_cloud(monkeypatch):
    _leer()
    _skill("wochenplan", beschreibung="Woche planen")
    monkeypatch.setattr(cloud, "_profil", lambda: gross)
    kopf = cloud._static_system(None, tutor_mode=False)
    assert "- wochenplan — Woche planen" in kopf
    assert kopf == cloud._static_system(None, tutor_mode=False)
    # Der Inhalt steht NICHT im Kopf — der kommt per load_skill.
    assert "Schritt eins." not in kopf


def test_klein_bekommt_keine_skill_liste(monkeypatch):
    _leer()
    _skill("wochenplan", beschreibung="Woche planen")
    monkeypatch.setattr(cloud, "_profil", lambda: klein)
    assert "wochenplan" not in cloud._static_system(None, tutor_mode=False)


def test_klein_hat_keine_skill_werkzeuge():
    namen = {t["function"]["name"] for t in klein.TOOLS}
    assert not namen & {"load_skill", "propose_skill", "edit_skill"}
    namen = {t["function"]["name"] for t in gross.TOOLS}
    assert {"load_skill", "propose_skill", "edit_skill"} <= namen


def test_meta_regel_nennt_laden_vorschlagen_und_hausregeln():
    kopf = gross.system()
    assert "load_skill" in kopf and "propose_skill" in kopf
    assert "Hausregeln" in kopf


# ── load_skill ────────────────────────────────────────────────────────

def test_load_skill_liefert_den_inhalt_ungefragt():
    _leer()
    _skill("recherche", inhalt="1. suchen\n2. lesen")
    fragen, erg = _werkzeug("load_skill", {"name": "Recherche"}, "nein")
    assert fragen == []
    assert erg[0] == "result" and "1. suchen\n2. lesen" in erg[1]
    assert "- beschreibung" not in erg[1]


def test_load_skill_unbekannt_nennt_die_aktiven():
    _leer()
    _skill("kurz")
    erg = skills.laden("gibtsnicht")
    assert "Keinen Skill" in erg and "kurz" in erg


def test_load_skill_gibt_ausgeschaltete_nicht_heraus():
    _leer()
    _skill("alt", status="aus", inhalt="GEHEIM")
    assert "GEHEIM" not in skills.laden("alt")
    assert "nicht aktiv" in skills.laden("alt")


def test_load_skill_kein_pfad_ausbruch():
    _leer()
    assert "Keinen Skill" in skills.laden("../../ai_config")


# ── propose_skill: gegatet ────────────────────────────────────────────

_VORSCHLAG = {"name": "Einkauf", "beschreibung": "Wenn Sasha einkaufen geht",
              "inhalt": "Liste lesen\nnach Laden sortieren\nfehlende fragen\nfertig"}


def test_propose_skill_ja_legt_an():
    _leer()
    fragen, erg = _werkzeug("propose_skill", _VORSCHLAG, "ja")
    assert len(fragen) == 1
    # Die Frage zeigt Name, Beschreibung und den Anfang der Anleitung.
    assert "einkauf" in fragen[0] and "Wenn Sasha einkaufen geht" in fragen[0]
    assert "Liste lesen" in fragen[0] and "(+1 Zeilen)" in fragen[0]
    assert erg[0] == "result" and "angelegt" in erg[1]
    s = {x["name"]: x for x in skills.alle()}["einkauf"]
    assert (s["status"], s["herkunft"]) == ("aktiv", "ki")
    assert "Liste lesen" in skills.laden("einkauf")


def test_propose_skill_nein_legt_nichts_an():
    _leer()
    fragen, erg = _werkzeug("propose_skill", _VORSCHLAG, "nein")
    assert len(fragen) == 1
    assert "abgelehnt" in erg[1]
    assert os.listdir(_ordner()) == []


def test_propose_skill_ueberschreibt_keinen_bestehenden():
    _leer()
    _skill("einkauf", inhalt="ALT")
    _, erg = _werkzeug("propose_skill", _VORSCHLAG, "ja")
    assert "gibt es schon" in erg[1]
    assert "ALT" in skills.laden("einkauf")


@pytest.mark.parametrize("args, fehler", [
    ({"name": "", "beschreibung": "x", "inhalt": "y"}, "kein Name"),
    ({"name": "a", "beschreibung": " ", "inhalt": "y"}, "keine Beschreibung"),
    ({"name": "a", "beschreibung": "x" * 200, "inhalt": "y"}, "zu lang"),
    ({"name": "a", "beschreibung": "x", "inhalt": ""}, "leerer Inhalt"),
    ({"name": "a", "beschreibung": "x", "inhalt": "y" * 7000}, "Zu lang"),
])
def test_propose_skill_fehlerfaelle(args, fehler):
    _leer()
    erg = skills.vorschlagen(args["name"], args["beschreibung"], args["inhalt"])
    assert fehler in erg
    assert os.listdir(_ordner()) == []


def test_skill_werkzeuge_im_gate():
    assert werkzeug_register.braucht_erlaubnis("propose_skill", {})
    assert werkzeug_register.braucht_erlaubnis("edit_skill", {})
    assert not werkzeug_register.braucht_erlaubnis("load_skill", {"name": "x"})


# ── edit_skill ────────────────────────────────────────────────────────

def test_edit_skill_ersetzt_inhalt_behaelt_kopf_und_legt_bak():
    _leer()
    _skill("kurz", inhalt="ALT", herkunft="sasha")
    fragen, erg = _werkzeug("edit_skill", {"name": "kurz", "inhalt": "NEU"}, "ja")
    assert len(fragen) == 1 and "kurz" in fragen[0] and ".bak" in fragen[0]
    assert "neu geschrieben" in erg[1]
    assert "NEU" in skills.laden("kurz") and "ALT" not in skills.laden("kurz")
    s = {x["name"]: x for x in skills.alle()}["kurz"]
    assert (s["status"], s["herkunft"]) == ("aktiv", "sasha")
    with open(os.path.join(_ordner(), "kurz.md.bak")) as f:
        assert "ALT" in f.read()
    # Die .bak ist kein eigener Skill.
    assert [x["name"] for x in skills.alle()] == ["kurz"]


def test_edit_skill_nein_aendert_nichts():
    _leer()
    _skill("kurz", inhalt="ALT")
    _, erg = _werkzeug("edit_skill", {"name": "kurz", "inhalt": "NEU"}, "nein")
    assert "abgelehnt" in erg[1]
    assert "ALT" in skills.laden("kurz")
    assert not os.path.exists(os.path.join(_ordner(), "kurz.md.bak"))


def test_edit_skill_nur_fuer_bestehende():
    _leer()
    erg = skills.aendern("gibtsnicht", "x")
    assert "nur bestehende" in erg
    assert os.listdir(_ordner()) == []


def test_edit_skill_wirft_mitgeschickten_kopf_weg():
    """Status und Herkunft ändert nur Sasha — auch wenn das Modell den Kopf
    mit einem anderen Status zurückschickt."""
    _leer()
    _skill("kurz", status="aktiv", herkunft="sasha")
    skills.aendern("kurz", "## kurz\n- status: aus\n- herkunft: ki\n\nNEU")
    s = {x["name"]: x for x in skills.alle()}["kurz"]
    assert (s["status"], s["herkunft"]) == ("aktiv", "sasha")
    assert "NEU" in skills.laden("kurz")


def test_edit_skill_laesst_eigene_ueberschriften_stehen():
    _leer()
    _skill("kurz")
    skills.aendern("kurz", "## Ablauf\n- erst: lesen\n\ndann schreiben")
    assert "## Ablauf" in skills.laden("kurz")


# ── Erstbefüllung ─────────────────────────────────────────────────────

def test_erster_zugriff_bringt_die_vorlagen():
    namen = [s["name"] for s in skills.alle()]
    vorlagen = sorted(f[:-3] for f in os.listdir(skills.VORLAGEN_DIR)
                      if f.endswith(".md"))
    assert namen == vorlagen and len(vorlagen) == 3
    assert all(s["status"] == "aktiv" and s["herkunft"] == "sasha"
               and s["beschreibung"] for s in skills.alle())


def test_vorlagen_sind_gueltig_und_knapp():
    for s in skills.alle():
        assert len(s["beschreibung"]) <= skills.MAX_BESCHREIBUNG
        assert "Skill" in skills.laden(s["name"])


def test_erstbefuellung_ueberschreibt_nie(tmp_path):
    ziel = str(tmp_path / "eigen")
    os.makedirs(ziel)
    with open(os.path.join(ziel, "kurz.md"), "w") as f:
        f.write("SASHAS FASSUNG")
    angelegt = skills.erstbefuellen(ziel)
    assert "kurz" not in angelegt
    with open(os.path.join(ziel, "kurz.md")) as f:
        assert f.read() == "SASHAS FASSUNG"


def test_vorhandener_ordner_wird_nicht_wieder_befuellt():
    """Hat Sasha die Skills einmal bekommen (Ordner da), kommt nichts zurück."""
    _leer()
    assert skills.alle() == []


def test_erstbefuellte_dateien_sind_alt_datiert():
    """Sonst gewänne beim Sync (neueste Datei gewinnt) die frische Vorlage
    eines neuen Rechners gegen Sashas Änderung auf dem anderen."""
    skills.alle()
    for datei in os.listdir(_ordner()):
        assert os.path.getmtime(os.path.join(_ordner(), datei)) == skills._VORLAGEN_ZEIT


# ── Route ─────────────────────────────────────────────────────────────

def test_route_listet_alle_skills():
    from ui.app import app
    _leer()
    _skill("a", status="aus")
    _skill("b")
    r = app.test_client().get("/api/skills")
    assert r.status_code == 200
    liste = r.get_json()["skills"]
    assert [(s["name"], s["status"]) for s in liste] == [("a", "aus"), ("b", "aktiv")]
    assert set(liste[0]) == {"name", "beschreibung", "status", "herkunft", "erstellt"}

