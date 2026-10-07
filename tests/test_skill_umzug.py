"""Umzug der alten Skill-Dateien ins Claude-Format (core/skill_umzug.py,
2026-10-07): alte `<name>.md` → `<name>/SKILL.md` + `_zentrale.json`, beim
ersten Zugriff, wiederholbar ohne Wirkung, nichts gelöscht (beiseite nach
`_alt/`); `kurz` wird eine Hausregel und aus, `recherche` bekommt den
Vermerk „Kandidat zum Ersetzen".

Geprobt an einer KOPIE der Vorlagen-Texte, wie sie bis heute in
data/gedaechtnis/skills/ liegen — nie am echten data/."""
import json
import os
import shutil

import pytest

import gedaechtnis
import skill_format
import skill_umzug
import skills
import state

ALT = {
    "kurz": ("## kurz\n- beschreibung: Sasha ist im Stress, unterwegs oder sagt „kurz“ — knapp antworten, eine Sache nach der anderen.\n"
             "- erstellt:     2026-10-07\n- herkunft:     sasha\n- status:       aktiv\n\n"
             "- Die Antwort zuerst, in einem bis drei Sätzen.\n"),
    "recherche": ("## recherche\n- beschreibung: Sasha will etwas Aktuelles oder Genaues wissen.\n"
                  "- erstellt:     2026-10-07\n- herkunft:     sasha\n- status:       aktiv\n\n"
                  "1. Erst search_memory.\n2. web_search.\n"),
    "wochenplan": ("## wochenplan\n- beschreibung: Sasha will wissen, was diese Woche ansteht.\n"
                   "- erstellt:     2026-10-07\n- herkunft:     sasha\n- status:       aktiv\n\n"
                   "1. Kalender lesen: read_calendar.\n2. Zusammenfassen.\n"),
}
ALTE_ZEIT = 1_790_000_000.0


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "x.json"))


def _ordner():
    return gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)


def _alt_anlegen(namen=("kurz", "recherche", "wochenplan"), **ersetzt):
    os.makedirs(_ordner(), exist_ok=True)
    for n in namen:
        p = os.path.join(_ordner(), n + ".md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(ersetzt.get(n, ALT[n]))
        os.utime(p, (ALTE_ZEIT, ALTE_ZEIT))


def _hausregeln():
    return gedaechtnis.kernakte_lesen("hausregeln")


def test_alte_dateien_ziehen_um_ins_claude_format():
    _alt_anlegen()
    alle = {s["name"]: s for s in skills.alle()}
    assert set(alle) == {"kurz", "recherche", "wochenplan"}
    w = alle["wochenplan"]
    assert (w["status"], w["herkunft"], w["erstellt"]) == ("aktiv", "sasha", "2026-10-07")
    assert w["beschreibung"] == "Sasha will wissen, was diese Woche ansteht."
    with open(os.path.join(_ordner(), "wochenplan", "SKILL.md"), encoding="utf-8") as f:
        _, felder, rest = skill_format.zerlegen(f.read())
    assert felder["name"] == "wochenplan"
    assert rest.startswith("1. Kalender lesen")
    assert "1. Kalender lesen" in skills.laden("wochenplan")


def test_nichts_geloescht_alte_liegen_beiseite():
    _alt_anlegen()
    skills.alle()
    alt = os.path.join(_ordner(), "_alt")
    assert sorted(os.listdir(alt)) == ["kurz.md", "recherche.md", "wochenplan.md"]
    with open(os.path.join(alt, "kurz.md"), encoding="utf-8") as f:
        assert f.read() == ALT["kurz"]
    assert not [d for d in os.listdir(_ordner()) if d.endswith(".md")]


def test_kurz_wird_hausregel_und_aus():
    _alt_anlegen()
    alle = {s["name"]: s for s in skills.alle()}
    assert alle["kurz"]["status"] == "aus" and "Hausregel" in alle["kurz"]["vermerk"]
    assert "kurz" not in skills.prompt_block()
    regeln = _hausregeln()
    assert skill_umzug.KURZ_REGEL in regeln
    assert regeln.startswith("# Hausregeln")


def test_kurz_haengt_an_bestehende_hausregeln_an_mit_bak():
    gedaechtnis.kernakte_schreiben("hausregeln", "# Hausregeln\n\n- Nicht duzen.\n")
    _alt_anlegen(("kurz",))
    skills.alle()
    regeln = _hausregeln()
    assert regeln.startswith("# Hausregeln\n\n- Nicht duzen.\n- Bin ich im Stress")
    bak = os.path.join(gedaechtnis._DIR, "hausregeln.md.bak")
    with open(bak, encoding="utf-8") as f:
        assert f.read() == "# Hausregeln\n\n- Nicht duzen.\n"


def test_kurz_ausgeschaltet_wird_keine_hausregel():
    _alt_anlegen(("kurz",), kurz=ALT["kurz"].replace("status:       aktiv", "status:       aus"))
    skills.alle()
    assert skill_umzug.KURZ_REGEL not in _hausregeln()


def test_recherche_bekommt_vermerk():
    _alt_anlegen(("recherche",))
    s = skills.alle()[0]
    assert s["status"] == "aktiv" and "Kandidat zum Ersetzen" in s["vermerk"]


def test_umzug_ist_idempotent():
    _alt_anlegen()
    skills.alle()
    stand = {}
    for ort, _, dateinamen in os.walk(gedaechtnis._DIR):
        for d in dateinamen:
            p = os.path.join(ort, d)
            with open(p, "rb") as f:
                stand[p] = f.read()
    skills.alle()
    skills.prompt_block()
    nachher = {}
    for ort, _, dateinamen in os.walk(gedaechtnis._DIR):
        for d in dateinamen:
            p = os.path.join(ort, d)
            with open(p, "rb") as f:
                nachher[p] = f.read()
    assert nachher == stand
    assert _hausregeln().count("Bin ich im Stress") == 1


def test_vom_anderen_rechner_zurueckgekommene_alte_datei():
    """Der Sync bringt die alte Datei zurück, solange der andere Rechner
    nicht umgezogen ist: kein zweiter Umzug, keine zweite Hausregel, der
    neue Ordner (mit Sashas Schalter) bleibt."""
    _alt_anlegen()
    skills.alle()
    skills.status_setzen("wochenplan", "aus")
    _alt_anlegen()                                   # „vom Sync zurück"
    alle = {s["name"]: s for s in skills.alle()}
    assert alle["wochenplan"]["status"] == "aus"
    assert _hausregeln().count("Bin ich im Stress") == 1
    assert sorted(os.listdir(os.path.join(_ordner(), "_alt"))) == [
        "kurz.md", "recherche.md", "wochenplan.md"]


def test_abweichende_zurueckgekommene_fassung_wird_nicht_ueberschrieben():
    _alt_anlegen(("wochenplan",))
    skills.alle()
    _alt_anlegen(("wochenplan",), wochenplan=ALT["wochenplan"] + "ANDERS\n")
    skills.alle()
    alt = os.path.join(_ordner(), "_alt")
    assert sorted(os.listdir(alt)) == ["wochenplan.md", "wochenplan.md.2"]


def test_neue_dateien_tragen_die_zeit_der_alten():
    """Zieht der zweite Rechner später um, darf seine Fassung keinen
    Schalter überschreiben, den Sasha auf dem ersten schon umgelegt hat."""
    _alt_anlegen(("wochenplan",))
    skills.alle()
    for d in ("SKILL.md", "_zentrale.json"):
        assert os.path.getmtime(os.path.join(_ordner(), "wochenplan", d)) == ALTE_ZEIT


def test_alte_bak_und_kaputte_dateien():
    _alt_anlegen(("wochenplan",))
    with open(os.path.join(_ordner(), "wochenplan.md.bak"), "w") as f:
        f.write("ALTE FASSUNG")
    with open(os.path.join(_ordner(), "ohnekopf.md"), "w") as f:
        f.write("einfach Text\n")
    alle = {s["name"]: s for s in skills.alle()}
    assert alle["ohnekopf"]["status"] == "aus"       # wie vorher: ohne Kopf aus
    assert "wochenplan.md.bak" in os.listdir(os.path.join(_ordner(), "_alt"))


def test_mit_kopie_der_echten_daten(tmp_path):
    """Probe mit einer Kopie dessen, was heute wirklich in data/ liegt (nur
    gelesen, falls da). Ohne echte Daten: übersprungen."""
    haupt = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    haupt = haupt.split(os.sep + ".claude" + os.sep + "worktrees" + os.sep)[0]
    echt = os.path.join(haupt, "data", "gedaechtnis", "skills")
    if not os.path.isdir(echt) or not any(f.endswith(".md") for f in os.listdir(echt)):
        pytest.skip("keine alten Skill-Dateien auf diesem Rechner")
    shutil.copytree(echt, _ordner())
    vorher = {f for f in os.listdir(_ordner()) if f.endswith(".md")}
    alle = {s["name"]: s for s in skills.alle()}
    for datei in vorher:
        assert datei[:-3] in alle
        assert os.path.isfile(os.path.join(_ordner(), "_alt", datei))
    if "kurz" in alle:
        assert alle["kurz"]["status"] == "aus"
