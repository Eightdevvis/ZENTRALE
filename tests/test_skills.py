"""Skills (Phase 4 des Claude-Web-Plans, 2026-10-07; seit dem Abend im
Format von Claude): ein Skill = Ordner mit SKILL.md (YAML-Kopf name +
description) und optional scripts/, references/, assets/; ZENTRALEs eigene
Angaben in _zentrale.json daneben. Im festen Prompt nur die Liste, die
Anleitung per load_skill, Dateien per load_skill(datei=…), Skripte nur in
der Sandbox. Anlegen (propose_skill) und Umschreiben (edit_skill) nur nach
Sashas Ja.

Geprüft wird Verhalten:
  - die Liste im Prompt ist deterministisch, zeigt nur aktive, bleibt unter
    LISTE_MAX — Beschreibungen vollständig; nur als letzte Rettung bekommen
    die längsten eine Kurzfassung, dann nur den Namen (seit 2026-10-08),
  - load_skill liefert Anleitung + Dateiliste, Dateien ohne Pfad-Ausbruch,
    und nur von aktiven,
  - propose/edit_skill schreiben Claude-taugliche SKILL.md, gegatet, .bak,
  - die Erstbefüllung (eigene + Anthropic) überschreibt nie, liefert
    Lizenz und Status/braucht mit,
  - klein bleibt unverändert.
Umzug alter Dateien: tests/test_skill_umzug.py. Format: test_skill_format.py.
Wächter gegen das echte data/: tests/test_keine_seiteneffekte.py.
"""
import json
import os

import pytest

import cloud
import gedaechtnis
import ki_werkzeuge
import skill_format
import skills
import state
import werkzeug_register
import werkzeug_schleife
from profil import gross, klein

ECHTE_VORLAGEN = skills.VORLAGEN_DIR
ECHTE_ANTHROPIC = skills.ANTHROPIC_DIR
ECHTER_STATUS = skills.ANTHROPIC_STATUS


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    # Ohne Vorlagen, damit jeder Test nur seine eigenen Skills sieht. Die
    # echten Vorlagen holt die Fixture `echte_vorlagen` zurück.
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_DIR", str(leer / "anthropic"))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "anthropic" / "zentrale.json"))


@pytest.fixture
def echte_vorlagen(monkeypatch):
    monkeypatch.setattr(skills, "VORLAGEN_DIR", ECHTE_VORLAGEN)
    monkeypatch.setattr(skills, "ANTHROPIC_DIR", ECHTE_ANTHROPIC)
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", ECHTER_STATUS)


def _ordner():
    return gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)


def _skill(name, status="aktiv", beschreibung=None, inhalt="Schritt eins.",
           herkunft="sasha", dateien=None, zentrale=True, kopf_extra=""):
    pfad = os.path.join(_ordner(), name)
    os.makedirs(pfad, exist_ok=True)
    with open(os.path.join(pfad, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ndescription: {beschreibung or 'wenn ' + name}\n"
                f"{kopf_extra}---\n\n{inhalt}\n")
    if zentrale:
        with open(os.path.join(pfad, "_zentrale.json"), "w", encoding="utf-8") as f:
            json.dump({"status": status, "herkunft": herkunft,
                       "erstellt": "2026-10-07"}, f)
    for rel, text in (dateien or {}).items():
        ziel = os.path.join(pfad, rel)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb" if isinstance(text, bytes) else "w") as f:
            f.write(text)
    return pfad


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
    _skill("b")
    _skill("a")
    assert skills.prompt_block() == skills.prompt_block()


def test_mehrzeilige_beschreibung_wird_eine_zeile():
    _skill("lang", beschreibung=">\n  erste Zeile\n  zweite Zeile\n")
    assert "- lang — erste Zeile zweite Zeile" in skills.prompt_block()


def test_ohne_beschreibung_zaehlt_als_aus():
    _skill("leer", beschreibung="''")
    assert skills.prompt_block() == ""
    assert [s["status"] for s in skills.alle()] == ["aus"]


def test_ohne_kopf_zaehlt_als_aus():
    pfad = os.path.join(_ordner(), "kaputt")
    os.makedirs(pfad)
    with open(os.path.join(pfad, "SKILL.md"), "w") as f:
        f.write("einfach Text\n")
    assert skills.prompt_block() == ""
    assert [s["status"] for s in skills.alle()] == ["aus"]


def test_hineinkopierter_claude_skill_ohne_zentrale_json_ist_an():
    """Ziel 2026-10-07: echte Claude-Skills ohne Umbau hineinkopieren."""
    _skill("fremd", zentrale=False,
           kopf_extra="license: Apache-2.0\nmetadata:\n  version: '1.0'\nallowed-tools: Read\n")
    s = skills.alle()[0]
    assert (s["name"], s["status"], s["herkunft"]) == ("fremd", "aktiv", "-")
    assert "- fremd — wenn fremd" in skills.prompt_block()


def test_ungueltige_ordner_und_eigenes_werden_uebergangen():
    _skill("gut")
    for name in ("_alt", ".versteckt", "Gross_Schreibung"):
        os.makedirs(os.path.join(_ordner(), name))
        with open(os.path.join(_ordner(), name, "SKILL.md"), "w") as f:
            f.write("---\nname: x\ndescription: y\n---\n")
    assert [s["name"] for s in skills.alle()] == ["gut"]


def test_ohne_aktive_skills_kein_block():
    assert skills.prompt_block() == ""


def _lang(i, n=900):
    """Eine lange Beschreibung mit erkennbarem erstem Satz."""
    return f"Wenn es um Thema {i} geht. " + "x" * (n - 24)


def _zeile(block, name):
    return [z for z in block.splitlines() if z.startswith(f"- {name} — ")][0]


def test_liste_passt_beschreibungen_vollstaendig():
    """Sasha 08.10.2026: gleichmäßig kürzen verschlechtert alle — passt die
    Liste, steht jede Beschreibung ganz da."""
    for i in range(5):
        _skill(f"s{i}", beschreibung=_lang(i))
    block = skills.prompt_block()
    assert len(block) <= skills.LISTE_MAX and "…" not in block
    assert _zeile(block, "s3") == "- s3 — " + _lang(3)
    lage = skills.liste_lage()
    assert lage["laenge"] == len(block) and not lage["zu_lang"]
    assert lage["gekuerzt"] == lage["nur_name"] == []


def test_zu_lang_kuerzt_nur_die_laengsten_und_laesst_kurze_ganz():
    for i in range(7):
        _skill(f"lang{i}", beschreibung=_lang(i, 900 + i * 10))   # lang6 am längsten
    for i in range(3):
        _skill(f"kurz{i}", beschreibung=f"Kurz und klar {i}.")
    block = skills.prompt_block()
    assert len(block) <= skills.LISTE_MAX
    lage = skills.liste_lage()
    assert lage["zu_lang"] and lage["laenge"] > skills.LISTE_MAX
    assert lage["grenze"] == skills.LISTE_MAX and lage["nur_name"] == []
    # Die längsten zuerst, nur so viele wie nötig — der Rest bleibt ganz.
    assert lage["gekuerzt"] and "lang6" in lage["gekuerzt"] and "lang0" not in lage["gekuerzt"]
    assert _zeile(block, "lang0") == "- lang0 — " + _lang(0, 900)
    for i in range(3):
        assert _zeile(block, f"kurz{i}") == f"- kurz{i} — Kurz und klar {i}."
    # Kurzfassung = erster Satz, aber nie unter MIN_BESCHREIBUNG
    kurz = _zeile(block, "lang6")[len("- lang6 — "):]
    assert kurz.startswith("Wenn es um Thema 6 geht.") and len(kurz) == skills.MIN_BESCHREIBUNG
    assert block == skills.prompt_block()


def test_gleich_lange_werden_nach_name_gekuerzt():
    """Deterministisch auch bei Gleichstand — sonst bräche der Prompt-Cache."""
    for i in range(7):
        _skill(f"s{i}", beschreibung=_lang(i))
    lage = skills.liste_lage()
    n = len(lage["gekuerzt"])
    assert 0 < n < 7 and lage["gekuerzt"] == [f"s{i}" for i in range(n)]


def test_liste_viel_zu_lang_nennt_die_laengsten_nur_mit_namen():
    for i in range(60):
        _skill(f"s{i:02d}", beschreibung="y" * 500)
    block = skills.prompt_block()
    assert len(block) <= skills.LISTE_MAX
    assert "ohne Beschreibung (zu viele): " in block
    assert all(f"s{i:02d}" in block for i in range(60))
    lage = skills.liste_lage()
    assert lage["nur_name"] and len(lage["gekuerzt"]) == 60
    assert lage["nur_name"][0] == "s00"                  # Gleichstand: nach Name


def test_kurzfassung():
    satz = "Erstellt Tabellen aus Daten. " + "Mehr dazu " * 40
    assert skills.kurzfassung(satz).startswith("Erstellt Tabellen aus Daten. Mehr")
    # bis MIN_BESCHREIBUNG (ein Leerzeichen am Schnitt fällt weg)
    assert skills.MIN_BESCHREIBUNG - 1 <= len(skills.kurzfassung(satz)) <= skills.MIN_BESCHREIBUNG
    mittel = "a" * 200 + ". " + "b" * 400
    assert skills.kurzfassung(mittel) == "a" * 200 + "."
    ohne_ende = "c" * 900
    assert len(skills.kurzfassung(ohne_ende)) == skills.KURZ_MAX
    assert skills.kurzfassung("kurz") == "kurz"


def test_eine_beschreibung_hoechstens_1024_im_kopf():
    _skill("riese", beschreibung="z" * 3000)
    zeile = [z for z in skills.prompt_block().splitlines() if z.startswith("- riese")][0]
    assert len(zeile) == len("- riese — ") + skills.MAX_BESCHREIBUNG


def test_liste_steht_im_festen_teil_der_cloud(monkeypatch):
    _skill("wochenplan", beschreibung="Woche planen")
    monkeypatch.setattr(cloud, "_profil", lambda: gross)
    kopf = cloud._static_system(None, tutor_mode=False)
    assert "- wochenplan — Woche planen" in kopf
    assert kopf == cloud._static_system(None, tutor_mode=False)
    # Der Inhalt steht NICHT im Kopf — der kommt per load_skill.
    assert "Schritt eins." not in kopf


def test_klein_bekommt_keine_skill_liste(monkeypatch):
    _skill("wochenplan", beschreibung="Woche planen")
    monkeypatch.setattr(cloud, "_profil", lambda: klein)
    assert "wochenplan" not in cloud._static_system(None, tutor_mode=False)


def test_klein_hat_keine_skill_werkzeuge():
    namen = {t["function"]["name"] for t in klein.TOOLS}
    assert not namen & {"load_skill", "propose_skill", "edit_skill"}
    namen = {t["function"]["name"] for t in gross.TOOLS}
    assert {"load_skill", "propose_skill", "edit_skill"} <= namen
    schema = {t["function"]["name"]: t["function"]["parameters"]["properties"]
              for t in gross.TOOLS}
    assert {"name", "datei", "ab"} <= set(schema["load_skill"])
    assert "skill" in schema["run_code"]


def test_meta_regel_nennt_laden_vorschlagen_und_hausregeln():
    kopf = gross.system()
    assert "load_skill" in kopf and "propose_skill" in kopf
    assert "Hausregeln" in kopf


# ── load_skill ────────────────────────────────────────────────────────

def test_load_skill_liefert_die_anleitung_ungefragt():
    _skill("recherche", inhalt="1. suchen\n2. lesen")
    fragen, erg = _werkzeug("load_skill", {"name": "Recherche"}, "nein")
    assert fragen == []
    assert erg[0] == "result" and "1. suchen\n2. lesen" in erg[1]
    assert "description:" not in erg[1]          # der Kopf steht in der Liste


def test_load_skill_nennt_dateien_aber_nicht_lizenz_und_zentrale():
    _skill("mit", dateien={"references/a.md": "A", "scripts/x.py": "print(1)",
                           "LICENSE.txt": "Apache", "assets/b.png": b"\x89PNG"})
    text = skills.laden("mit")
    assert "references/a.md" in text and "scripts/x.py" in text
    assert "assets/b.png" in text
    assert "LICENSE.txt" not in text and "_zentrale.json" not in text
    assert "run_code" in text and "/skills/mit" in text


def test_load_skill_weist_auf_zentrale_hinweis_hin():
    _skill("fremd", dateien={"references/zentrale.md": "Hier geht nur …"})
    text = skills.laden("fremd")
    assert text.index("references/zentrale.md") < text.index("Schritt eins.")


def test_load_skill_lange_anleitung_seitenweise():
    _skill("lang", inhalt="a" * (skills.SEITE + 500))
    erste = skills.laden("lang")
    assert f"ab={skills.SEITE}" in erste
    zweite = skills.laden("lang", ab=skills.SEITE)
    assert zweite.strip() == "a" * 500


def test_load_skill_datei_lesen():
    _skill("mit", dateien={"references/a.md": "Nachlesestoff"})
    fragen, erg = _werkzeug("load_skill", {"name": "mit", "datei": "references/a.md"}, "nein")
    assert fragen == [] and "Nachlesestoff" in erg[1]


@pytest.mark.parametrize("datei", ["../anderer/SKILL.md", "/etc/passwd",
                                   "../../hausregeln.md", "references/../../anderer/SKILL.md",
                                   "verweis.md", "."])
def test_load_skill_datei_kein_pfad_ausbruch(datei):
    _skill("anderer", inhalt="GEHEIM")
    pfad = _skill("mit")
    os.symlink(os.path.join(_ordner(), "anderer", "SKILL.md"),
               os.path.join(pfad, "verweis.md"))
    text = skills.laden("mit", datei)
    assert "GEHEIM" not in text and "root:" not in text
    assert text.startswith("[")


def test_load_skill_datei_fehlt_oder_ist_ordner_oder_binaer():
    _skill("mit", dateien={"references/a.md": "A", "assets/b.png": b"\x89PNG\xff\xfe"})
    assert "Keine Datei" in skills.laden("mit", "references/gibtsnicht.md")
    assert "references/a.md" in skills.laden("mit", "references")
    assert "keine Textdatei" in skills.laden("mit", "assets/b.png")


def test_load_skill_unbekannt_nennt_die_aktiven():
    _skill("wochenplan")
    erg = skills.laden("gibtsnicht")
    assert "Keinen Skill" in erg and "wochenplan" in erg


def test_load_skill_gibt_ausgeschaltete_nicht_heraus():
    _skill("alt", status="aus", inhalt="GEHEIM", dateien={"references/r.md": "AUCH"})
    assert "GEHEIM" not in skills.laden("alt")
    assert "nicht aktiv" in skills.laden("alt")
    assert "AUCH" not in skills.laden("alt", "references/r.md")


def test_load_skill_kein_pfad_ausbruch_ueber_den_namen():
    assert "Keinen Skill" in skills.laden("../../ai_config")


def test_skript_ordner_nur_fuer_aktive():
    pfad = _skill("an")
    _skill("aus", status="aus")
    assert skills.skript_ordner("an") == (os.path.realpath(pfad), None)
    ordner, fehler = skills.skript_ordner("aus")
    assert ordner is None and "nicht aktiv" in fehler
    assert skills.skript_ordner("../x")[0] is None


# ── propose_skill: gegatet, Claude-Format ─────────────────────────────

_VORSCHLAG = {"name": "Einkauf", "beschreibung": "Wenn Sasha einkaufen geht: Liste nach Laden sortieren",
              "inhalt": "Liste lesen\nnach Laden sortieren\nfehlende fragen\nfertig"}


def test_propose_skill_ja_legt_claude_skill_an():
    fragen, erg = _werkzeug("propose_skill", _VORSCHLAG, "ja")
    assert len(fragen) == 1
    # Die Frage zeigt Name, Beschreibung und den Anfang der Anleitung.
    assert "einkauf" in fragen[0] and "Wenn Sasha einkaufen geht" in fragen[0]
    assert "Liste lesen" in fragen[0] and "(+1 Zeilen)" in fragen[0]
    assert erg[0] == "result" and "angelegt" in erg[1]
    s = {x["name"]: x for x in skills.alle()}["einkauf"]
    assert (s["status"], s["herkunft"]) == ("aktiv", "ki")
    assert "Liste lesen" in skills.laden("einkauf")
    # Die SKILL.md ist Claude-tauglich: nur name + description im Kopf.
    with open(os.path.join(_ordner(), "einkauf", "SKILL.md"), encoding="utf-8") as f:
        roh, felder, rest = skill_format.zerlegen(f.read())
    assert felder == {"name": "einkauf", "description": _VORSCHLAG["beschreibung"]}
    assert rest.startswith("Liste lesen")


def test_propose_skill_nein_legt_nichts_an():
    fragen, erg = _werkzeug("propose_skill", _VORSCHLAG, "nein")
    assert len(fragen) == 1
    assert "abgelehnt" in erg[1]
    assert skills.alle() == []


def test_propose_skill_ueberschreibt_keinen_bestehenden():
    _skill("einkauf", inhalt="ALT")
    _, erg = _werkzeug("propose_skill", _VORSCHLAG, "ja")
    assert "gibt es schon" in erg[1]
    assert "ALT" in skills.laden("einkauf")


def test_propose_skill_lange_beschreibung_bis_1024():
    erg = skills.vorschlagen("lang", "x" * 1024, "Schritt")
    assert "angelegt" in erg


@pytest.mark.parametrize("args, fehler", [
    ({"name": "", "beschreibung": "x", "inhalt": "y"}, "kein Name"),
    ({"name": "a", "beschreibung": " ", "inhalt": "y"}, "keine Beschreibung"),
    ({"name": "a", "beschreibung": "x" * 1025, "inhalt": "y"}, "zu lang"),
    ({"name": "a", "beschreibung": "wenn a < b", "inhalt": "y"}, "< oder >"),
    ({"name": "a", "beschreibung": "x", "inhalt": ""}, "leerer Inhalt"),
    ({"name": "a", "beschreibung": "x", "inhalt": "y" * (skills.MAX_INHALT + 1)}, "Zu lang"),
])
def test_propose_skill_fehlerfaelle(args, fehler):
    os.makedirs(_ordner(), exist_ok=True)
    erg = skills.vorschlagen(args["name"], args["beschreibung"], args["inhalt"])
    assert fehler in erg
    assert os.listdir(_ordner()) == []


def test_skill_werkzeuge_im_gate():
    assert werkzeug_register.braucht_erlaubnis("propose_skill", {})
    assert werkzeug_register.braucht_erlaubnis("edit_skill", {})
    assert not werkzeug_register.braucht_erlaubnis("load_skill", {"name": "x"})
    assert not werkzeug_register.braucht_erlaubnis("load_skill", {"name": "x", "datei": "a"})


def test_run_code_frage_nennt_den_skill():
    frage = werkzeug_register.frage("run_code", {"code": "print(1)", "skill": "skill-creator"})
    assert "skill-creator" in frage and "nur lesen" in frage


# ── edit_skill ────────────────────────────────────────────────────────

def test_edit_skill_ersetzt_anleitung_behaelt_kopf_und_legt_bak():
    pfad = _skill("plan", inhalt="ALT", herkunft="sasha",
                  kopf_extra="license: Complete terms in LICENSE.txt\nmetadata:\n  a: 1\n")
    with open(os.path.join(pfad, "SKILL.md")) as f:
        alt = f.read()
    fragen, erg = _werkzeug("edit_skill", {"name": "plan", "inhalt": "NEU"}, "ja")
    assert len(fragen) == 1 and "plan" in fragen[0] and ".bak" in fragen[0]
    assert "neu geschrieben" in erg[1]
    assert "NEU" in skills.laden("plan") and "ALT" not in skills.laden("plan")
    with open(os.path.join(pfad, "SKILL.md")) as f:
        neu = f.read()
    # Der Kopf ist Zeichen für Zeichen derselbe — auch die fremden Felder.
    assert neu.split("---\n\n")[0] == alt.split("---\n\n")[0]
    s = {x["name"]: x for x in skills.alle()}["plan"]
    assert (s["status"], s["herkunft"]) == ("aktiv", "sasha")
    with open(os.path.join(pfad, "SKILL.md.bak")) as f:
        assert f.read() == alt
    assert [x["name"] for x in skills.alle()] == ["plan"]
    assert "SKILL.md.bak" not in skills.laden("plan")


def test_edit_skill_nein_aendert_nichts():
    pfad = _skill("plan", inhalt="ALT")
    _, erg = _werkzeug("edit_skill", {"name": "plan", "inhalt": "NEU"}, "nein")
    assert "abgelehnt" in erg[1]
    assert "ALT" in skills.laden("plan")
    assert not os.path.exists(os.path.join(pfad, "SKILL.md.bak"))


def test_edit_skill_nur_fuer_bestehende():
    os.makedirs(_ordner(), exist_ok=True)
    erg = skills.aendern("gibtsnicht", "x")
    assert "nur bestehende" in erg
    assert os.listdir(_ordner()) == []


def test_edit_skill_wirft_mitgeschickten_kopf_weg():
    """Name und Beschreibung ändert nur Sasha — auch wenn das Modell die
    ganze SKILL.md mit anderem Kopf zurückschickt."""
    _skill("plan", beschreibung="wenn plan")
    skills.aendern("plan", "---\nname: plan\ndescription: immer\n---\n\nNEU")
    s = {x["name"]: x for x in skills.alle()}["plan"]
    assert s["beschreibung"] == "wenn plan"
    text = skills.laden("plan")
    assert "NEU" in text and "description" not in text


def test_edit_skill_laesst_eigene_trennlinien_und_ueberschriften_stehen():
    _skill("plan")
    skills.aendern("plan", "## Ablauf\n- erst: lesen\n\ndann schreiben")
    assert "## Ablauf" in skills.laden("plan")


# ── Status ────────────────────────────────────────────────────────────

def test_status_setzen_schreibt_nur_zentrale_json():
    pfad = _skill("plan")
    with open(os.path.join(pfad, "SKILL.md")) as f:
        vorher = f.read()
    assert skills.status_setzen("plan", "aus")["status"] == "aus"
    with open(os.path.join(pfad, "SKILL.md")) as f:
        assert f.read() == vorher                  # Claude-Datei unberührt
    with open(os.path.join(pfad, "_zentrale.json")) as f:
        z = json.load(f)
    assert z["status"] == "aus" and z["herkunft"] == "sasha"   # Rest bleibt
    with pytest.raises(KeyError):
        skills.status_setzen("gibtsnicht", "aus")
    with pytest.raises(ValueError):
        skills.status_setzen("plan", "vielleicht")


def test_status_setzen_legt_zentrale_json_an_wenn_sie_fehlt():
    pfad = _skill("fremd", zentrale=False)
    skills.status_setzen("fremd", "aus")
    assert "nicht aktiv" in skills.laden("fremd")
    assert os.path.isfile(os.path.join(pfad, "_zentrale.json"))


# ── Erstbefüllung ─────────────────────────────────────────────────────

ANTHROPIC_ERLAUBT = {
    "skill-creator", "academy-guide", "algorithmic-art", "brand-guidelines",
    "canvas-design", "claude-api", "discernment-nudge", "frontend-design",
    "internal-comms", "mcp-builder", "slack-gif-creator", "theme-factory",
    "webapp-testing", "web-artifacts-builder"}


def test_erster_zugriff_bringt_eigene_und_anthropic_vorlagen(echte_vorlagen):
    alle = {s["name"]: s for s in skills.alle()}
    assert set(alle) == ANTHROPIC_ERLAUBT | {"wochenplan", "recherche", "import-memory",
                                             "pdf", "word"}
    assert "kurz" not in alle                      # kein Skill mehr (Sasha 07.10.)
    for name in ("wochenplan", "recherche"):
        assert (alle[name]["status"], alle[name]["herkunft"]) == ("aktiv", "sasha")
    # 2026-10-08: von ZENTRALE selbst geschrieben, nach Claudes Vorbild.
    assert (alle["import-memory"]["status"], alle["import-memory"]["herkunft"]) \
        == ("aktiv", "zentrale")
    assert "Kandidat zum Ersetzen" in alle["recherche"]["vermerk"]
    for name in ANTHROPIC_ERLAUBT:
        assert alle[name]["herkunft"] == "anthropic"
        # Lizenz reist mit.
        with open(os.path.join(_ordner(), name, "LICENSE.txt")) as f:
            assert "Apache License" in f.read()
        with open(os.path.join(_ordner(), name, "_zentrale.json")) as f:
            assert "683bc88" in json.load(f)["quelle"]


def test_anthropic_status_an_und_aus_mit_braucht(echte_vorlagen):
    alle = {s["name"]: s for s in skills.alle()}
    an = {n for n in ANTHROPIC_ERLAUBT if alle[n]["status"] == "aktiv"}
    assert "skill-creator" in an
    assert an == {"skill-creator", "academy-guide", "claude-api",
                  "discernment-nudge", "frontend-design", "internal-comms"}
    for n in ANTHROPIC_ERLAUBT - an:
        assert alle[n]["status"] == "aus" and alle[n]["braucht"], n
    for n in an:
        assert not alle[n]["braucht"], n


def test_anthropic_vorlagen_nur_mit_apache_lizenz():
    """Was in core/skill_vorlagen/anthropic/ liegt, ist genau die geprüfte
    Liste — mit Lizenz, ohne docx/pdf/pptx/xlsx/doc-coauthoring."""
    ordner = {n for n in os.listdir(ECHTE_ANTHROPIC)
              if os.path.isdir(os.path.join(ECHTE_ANTHROPIC, n))}
    assert ordner == ANTHROPIC_ERLAUBT
    with open(ECHTER_STATUS) as f:
        assert set(json.load(f)["skills"]) == ANTHROPIC_ERLAUBT
    for n in ordner:
        with open(os.path.join(ECHTE_ANTHROPIC, n, "LICENSE.txt")) as f:
            lizenz = f.read()
        assert "Apache License" in lizenz and "Version 2.0" in lizenz, n
    for datei in ("README.md", "THIRD_PARTY_NOTICES.md"):
        assert os.path.isfile(os.path.join(ECHTE_ANTHROPIC, datei))
    with open(os.path.join(ECHTE_ANTHROPIC, "README.md")) as f:
        readme = f.read()
    assert "683bc88" in readme and "Apache" in readme


def test_alle_vorlagen_sind_claude_gueltig(echte_vorlagen):
    """Name im Kopf = Ordnername, Beschreibung da — wie Claudes Prüfung."""
    for s in skills.alle():
        with open(os.path.join(_ordner(), s["name"], "SKILL.md"), encoding="utf-8") as f:
            _, felder, rest = skill_format.zerlegen(f.read())
        assert felder.get("name") == s["name"]
        assert s["beschreibung"] and rest


def test_start_liste_passt_ohne_kuerzen(echte_vorlagen):
    block = skills.prompt_block()
    assert len(block) <= skills.LISTE_MAX
    assert "ohne Beschreibung" not in block
    assert "- skill-creator — Create new skills" in block
    assert "- wochenplan — " in block and "algorithmic-art" not in block


def test_erstbefuellung_ueberschreibt_nie(echte_vorlagen, tmp_path):
    ziel = str(tmp_path / "eigen")
    os.makedirs(os.path.join(ziel, "wochenplan"))
    with open(os.path.join(ziel, "wochenplan", "SKILL.md"), "w") as f:
        f.write("SASHAS FASSUNG")
    angelegt = skills.erstbefuellen(ziel)
    assert "wochenplan" not in angelegt and "skill-creator" in angelegt
    with open(os.path.join(ziel, "wochenplan", "SKILL.md")) as f:
        assert f.read() == "SASHAS FASSUNG"
    assert not os.path.exists(os.path.join(ziel, "wochenplan", "_zentrale.json"))
    assert skills.erstbefuellen(ziel) == []        # zweites Mal: nichts


def test_ausgeschalteter_vorlagen_skill_bleibt_aus(echte_vorlagen):
    skills.alle()
    skills.status_setzen("skill-creator", "aus")
    skills.alle()
    assert {s["name"]: s for s in skills.alle()}["skill-creator"]["status"] == "aus"


def test_erstbefuellte_dateien_sind_alt_datiert(echte_vorlagen):
    """Sonst gewänne beim Sync (neueste Datei gewinnt) die frische Vorlage
    eines neuen Rechners gegen Sashas Änderung auf dem anderen."""
    skills.alle()
    for name in ("wochenplan", "skill-creator"):
        for ort, _, dateinamen in os.walk(os.path.join(_ordner(), name)):
            assert os.path.getmtime(ort) == skills._VORLAGEN_ZEIT
            for d in dateinamen:
                assert os.path.getmtime(os.path.join(ort, d)) == skills._VORLAGEN_ZEIT


def test_skill_creator_hat_zentrale_hinweis(echte_vorlagen):
    text = skills.laden("skill-creator", "references/zentrale.md")
    assert "claude -p" in text and "quick_validate.py" in text
    assert "Zuerst lesen" in skills.laden("skill-creator")


# ── Route ─────────────────────────────────────────────────────────────

def test_route_listet_alle_skills_mit_braucht():
    from ui.app import app
    _skill("a", status="aus")
    _skill("b")
    with open(os.path.join(_ordner(), "a", "_zentrale.json"), "w") as f:
        json.dump({"status": "aus", "braucht": "einen Browser"}, f)
    r = app.test_client().get("/api/skills")
    assert r.status_code == 200
    liste = r.get_json()["skills"]
    assert [(s["name"], s["status"]) for s in liste] == [("a", "aus"), ("b", "aktiv")]
    assert set(liste[0]) == {"name", "beschreibung", "status", "herkunft",
                             "erstellt", "braucht", "vermerk"}
    assert liste[0]["braucht"] == "einen Browser"
    lage = r.get_json()["skill_liste"]
    assert lage["grenze"] == skills.LISTE_MAX and lage["laenge"] > 0 and not lage["zu_lang"]
